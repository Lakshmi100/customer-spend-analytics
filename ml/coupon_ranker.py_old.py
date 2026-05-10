"""
Coupon ranking engine.

For each customer, scores every coupon in the catalog using three signals:

    affinity_score  (weight 0.5)  — how strongly does this customer over-index
                                    on the coupon's category vs population?
                                    From CATEGORY_AFFINITY.affinity_index.

    recency_score   (weight 0.3)  — has the customer transacted in this
                                    category recently? Recent = top of mind
                                    = higher coupon redemption likelihood.

    cluster_score   (weight 0.2)  — does the customer's cluster prefer this
                                    category? Captures peer behavior even
                                    when the individual signal is weak.

A small filter rule prevents over-saturation:
    - If affinity_index < 0.3, the coupon is excluded entirely.
      (The customer barely spends here — a coupon won't change behavior.)

Run from project root:
    python -m ml.coupon_ranker
"""

from pathlib import Path
from typing import List, Tuple

import joblib
import numpy as np
import pandas as pd

from ml.coupon_catalog import get_catalog_df
from ml.snowflake_io import query_snowflake

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"

# Score weights (must sum to 1.0)
WEIGHTS = {
    "affinity": 0.50,
    "recency":  0.30,
    "cluster":  0.20,
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9

# Filter: minimum affinity to even consider a coupon
MIN_AFFINITY_TO_CONSIDER = 0.3

# Recency: <30 days is "fresh", >365 days is "cold"
RECENCY_FRESH_DAYS = 30
RECENCY_COLD_DAYS = 365


def load_customer_clusters() -> pd.DataFrame:
    """Load the (customer_token, cluster) mapping from segmentation artifacts."""
    return pd.read_parquet(ARTIFACTS_DIR / "customer_clusters.parquet")


def load_category_affinity() -> pd.DataFrame:
    """Pull category_affinity from Snowflake."""
    return query_snowflake(
        "SELECT customer_token, category, affinity_index, spend_share, "
        "       days_since_last_txn "
        "FROM MARTS.CATEGORY_AFFINITY"
    )


def compute_cluster_category_preferences(
    affinity: pd.DataFrame, customer_clusters: pd.DataFrame
) -> pd.DataFrame:
    """
    For each (cluster, category), what's the average affinity_index?
    Used as the cluster_score signal — captures peer behavior.
    """
    merged = affinity.merge(
        customer_clusters[["customer_token", "cluster"]], on="customer_token"
    )
    return (
        merged.groupby(["cluster", "category"])
        ["affinity_index"]
        .mean()
        .reset_index(name="cluster_avg_affinity")
    )


def normalize_signal(s: pd.Series, lower: float, upper: float) -> pd.Series:
    """Linearly clip and rescale a series to [0, 1]."""
    return ((s.clip(lower, upper) - lower) / (upper - lower)).fillna(0)


def score_coupons_for_customer(
    customer_token: str,
    catalog: pd.DataFrame,
    customer_affinity: pd.DataFrame,
    cluster_prefs: pd.DataFrame,
    customer_cluster: int,
) -> pd.DataFrame:
    """
    Score every coupon in the catalog for one customer.
    Returns DataFrame with: coupon_id, merchant, category, score, components, reasoning.
    """
    df = catalog.merge(customer_affinity, on="category", how="left")

    # Fill missing — customer never transacted in this category
    df["affinity_index"] = df["affinity_index"].fillna(0)
    df["days_since_last_txn"] = df["days_since_last_txn"].fillna(9999)
    df["spend_share"] = df["spend_share"].fillna(0)

    # Filter: drop categories the customer barely uses
    df = df[df["affinity_index"] >= MIN_AFFINITY_TO_CONSIDER].copy()

    if df.empty:
        return df

    # Bring in cluster-level signal
    cluster_for_this = cluster_prefs[cluster_prefs["cluster"] == customer_cluster]
    df = df.merge(
        cluster_for_this[["category", "cluster_avg_affinity"]],
        on="category", how="left",
    )
    df["cluster_avg_affinity"] = df["cluster_avg_affinity"].fillna(0)

    # Build the three signals normalized to [0, 1]
    df["affinity_score"] = normalize_signal(df["affinity_index"], 0, 5)
    df["recency_score"] = 1 - normalize_signal(
        df["days_since_last_txn"], RECENCY_FRESH_DAYS, RECENCY_COLD_DAYS
    )
    df["cluster_score"] = normalize_signal(df["cluster_avg_affinity"], 0, 5)

    # Composite weighted score
    df["score"] = (
        WEIGHTS["affinity"] * df["affinity_score"]
        + WEIGHTS["recency"]  * df["recency_score"]
        + WEIGHTS["cluster"]  * df["cluster_score"]
    )

    # Human-readable reasoning string for each coupon
    df["reasoning"] = df.apply(_make_reasoning, axis=1)

    df["customer_token"] = customer_token
    df["customer_cluster"] = customer_cluster

    cols = [
        "customer_token", "customer_cluster", "coupon_id", "merchant_name",
        "category", "tier", "title", "discount_display",
        "score", "affinity_score", "recency_score", "cluster_score",
        "affinity_index", "days_since_last_txn", "spend_share", "reasoning",
    ]
    return df[cols].sort_values("score", ascending=False).reset_index(drop=True)


def _make_reasoning(row: pd.Series) -> str:
    """Generate a 1-sentence explanation for why this coupon was selected."""
    reasons = []
    affinity = row["affinity_index"]
    days = row["days_since_last_txn"]

    if affinity >= 3:
        reasons.append(f"strongly over-indexes on {row['category']} ({affinity:.1f}x avg)")
    elif affinity >= 1.5:
        reasons.append(f"over-indexes on {row['category']} ({affinity:.1f}x avg)")
    elif affinity >= 0.5:
        reasons.append(f"regular {row['category']} spender")

    if days <= 14:
        reasons.append(f"transacted just {int(days)} days ago")
    elif days <= 60:
        reasons.append(f"active in past {int(days)} days")

    if row["cluster_score"] >= 0.5:
        reasons.append("cluster peers also prefer this category")

    return "; ".join(reasons) if reasons else "general fit"


def rank_for_all_customers() -> pd.DataFrame:
    """Score top coupons for every customer. Used for batch evaluation."""
    print("Loading data...")
    customer_clusters = load_customer_clusters()
    affinity = load_category_affinity()
    catalog = get_catalog_df()
    cluster_prefs = compute_cluster_category_preferences(affinity, customer_clusters)

    print(f"  {len(customer_clusters):,} customers, {len(catalog)} coupons, "
          f"{len(cluster_prefs)} cluster-category prefs")

    print("Scoring coupons for every customer...")
    all_results = []
    for _, cust in customer_clusters.iterrows():
        cust_aff = affinity[affinity["customer_token"] == cust["customer_token"]]
        ranked = score_coupons_for_customer(
            customer_token=cust["customer_token"],
            catalog=catalog,
            customer_affinity=cust_aff,
            cluster_prefs=cluster_prefs,
            customer_cluster=cust["cluster"],
        )
        if not ranked.empty:
            all_results.append(ranked.head(3))  # keep top 3 per customer

    result = pd.concat(all_results, ignore_index=True)
    out = ARTIFACTS_DIR / "coupon_recommendations.parquet"
    result.to_parquet(out, index=False)
    print(f"\n✓ Wrote {len(result):,} (customer, coupon) recommendations to:\n  {out}")
    return result


def main():
    result = rank_for_all_customers()

    print("\n=== Sample recommendations ===")
    customer_clusters = load_customer_clusters()
    sample_personas = ["Luxury Seeker Vanessa", "College Student Sasha",
                       "Soccer Mom Linda", "Active Retiree Carol"]

    for persona in sample_personas:
        sample_token = customer_clusters[
            customer_clusters["persona_name"] == persona
        ]["customer_token"].iloc[0]
        cust_recs = result[result["customer_token"] == sample_token]
        if not cust_recs.empty:
            print(f"\n→ {persona}  (token: {sample_token[:8]}...)")
            for _, r in cust_recs.iterrows():
                print(f"   [{r['score']:.3f}] {r['merchant_name']:<22} "
                      f"{r['discount_display']:<12} — {r['title']}")
                print(f"             reason: {r['reasoning']}")


if __name__ == "__main__":
    main()
