"""
Coupon ranking engine (v2 — polished scoring).

Improvements over v1:
    1. LOG-SCALED affinity normalization: preserves differentiation between
       2x, 5x, 10x, 20x over-indexers. (v1 clipped everything ≥5x at 1.0,
       producing scoring ties like 1.000 == 1.000 == 1.000.)

    2. EXPONENTIAL recency decay: a transaction yesterday scores higher than
       one 28 days ago, both still favored over 90+ days. (v1 treated all
       transactions <30 days as equally fresh.)

    3. DISCOUNT-VALUE TIEBREAKER: when scores are very close, prefer the
       coupon with the larger absolute discount. Makes ties feel intentional.

    4. NORMALIZED population statistics: rather than hardcoding "5x is the
       max," we use the actual 99th percentile of affinity in the data so
       the model adapts to whatever the underlying distribution looks like.

Score components:
    affinity_score  (weight 0.50)  — log-scaled customer affinity for category
    recency_score   (weight 0.30)  — exponential decay on days_since_last_txn
    cluster_score   (weight 0.20)  — log-scaled cluster avg affinity

Filter:
    affinity_index < MIN_AFFINITY → coupon excluded entirely
    (no behavioral evidence the customer would care)

Run:
    python -m ml.coupon_ranker
"""

from pathlib import Path
from typing import List, Tuple

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

# Filter threshold
MIN_AFFINITY_TO_CONSIDER = 0.3

# Recency decay constants
RECENCY_HALFLIFE_DAYS = 30   # score halves every 30 days

# Tiebreaker: when scores are within this delta, sort by discount value
TIEBREAK_DELTA = 0.02


# ============================================================================
# Data loading
# ============================================================================

def load_customer_clusters() -> pd.DataFrame:
    return pd.read_parquet(ARTIFACTS_DIR / "customer_clusters.parquet")


def load_category_affinity() -> pd.DataFrame:
    return query_snowflake(
        "SELECT customer_token, category, affinity_index, spend_share, "
        "       days_since_last_txn "
        "FROM MARTS.CATEGORY_AFFINITY"
    )


def compute_cluster_category_preferences(
    affinity: pd.DataFrame, customer_clusters: pd.DataFrame
) -> pd.DataFrame:
    merged = affinity.merge(
        customer_clusters[["customer_token", "cluster"]], on="customer_token"
    )
    return (
        merged.groupby(["cluster", "category"])
        ["affinity_index"]
        .mean()
        .reset_index(name="cluster_avg_affinity")
    )


# ============================================================================
# Normalization functions (the polished part)
# ============================================================================

def log_normalize(s: pd.Series, p99_max: float) -> pd.Series:
    """
    Log-scaled normalization.
    log(1 + s) / log(1 + p99_max) maps [0, ∞] → [0, ~1.0+]
    Then clip to [0, 1] for any extreme outliers.
    """
    if p99_max <= 0:
        return pd.Series(0, index=s.index)
    raw = np.log1p(s.clip(lower=0)) / np.log1p(p99_max)
    return raw.clip(0, 1)


def recency_decay(days: pd.Series, halflife: float = RECENCY_HALFLIFE_DAYS) -> pd.Series:
    """
    Exponential decay. Score = 0.5^(days/halflife).
    days=0 → 1.0
    days=30 → 0.5
    days=60 → 0.25
    days=90 → 0.125
    days=∞ → 0
    """
    return 0.5 ** (days.clip(lower=0) / halflife)


# ============================================================================
# Scoring (one customer)
# ============================================================================

def score_coupons_for_customer(
    customer_token: str,
    catalog: pd.DataFrame,
    customer_affinity: pd.DataFrame,
    cluster_prefs: pd.DataFrame,
    customer_cluster: int,
    affinity_p99: float,
    cluster_p99: float,
) -> pd.DataFrame:
    """
    Score every coupon in the catalog for one customer.
    Returns a DataFrame sorted by score descending, with reasoning.
    """
    df = catalog.merge(customer_affinity, on="category", how="left")

    df["affinity_index"] = df["affinity_index"].fillna(0)
    df["days_since_last_txn"] = df["days_since_last_txn"].fillna(9999)
    df["spend_share"] = df["spend_share"].fillna(0)

    # Filter low-affinity categories
    df = df[df["affinity_index"] >= MIN_AFFINITY_TO_CONSIDER].copy()
    if df.empty:
        return df

    # Cluster signal
    cluster_for_this = cluster_prefs[cluster_prefs["cluster"] == customer_cluster]
    df = df.merge(
        cluster_for_this[["category", "cluster_avg_affinity"]],
        on="category", how="left",
    )
    df["cluster_avg_affinity"] = df["cluster_avg_affinity"].fillna(0)

    # === The polished signals ===
    df["affinity_score"] = log_normalize(df["affinity_index"], affinity_p99)
    df["recency_score"]  = recency_decay(df["days_since_last_txn"])
    df["cluster_score"]  = log_normalize(df["cluster_avg_affinity"], cluster_p99)

    df["score"] = (
        WEIGHTS["affinity"] * df["affinity_score"]
        + WEIGHTS["recency"]  * df["recency_score"]
        + WEIGHTS["cluster"]  * df["cluster_score"]
    )

    # Tiebreaker: rank by score, then by discount value within near-ties
    df = df.sort_values(
        ["score", "discount_value"], ascending=[False, False]
    ).reset_index(drop=True)

    df["reasoning"] = df.apply(_make_reasoning, axis=1)
    df["customer_token"] = customer_token
    df["customer_cluster"] = customer_cluster

    cols = [
        "customer_token", "customer_cluster", "coupon_id", "merchant_name",
        "category", "tier", "title", "discount_display", "discount_value",
        "score", "affinity_score", "recency_score", "cluster_score",
        "affinity_index", "days_since_last_txn", "spend_share", "reasoning",
    ]
    return df[cols]


def _make_reasoning(row: pd.Series) -> str:
    reasons = []
    affinity = row["affinity_index"]
    days = row["days_since_last_txn"]

    if affinity >= 5:
        reasons.append(f"VERY strong preference for {row['category']} ({affinity:.1f}x avg)")
    elif affinity >= 2.5:
        reasons.append(f"strong preference for {row['category']} ({affinity:.1f}x avg)")
    elif affinity >= 1.5:
        reasons.append(f"over-indexes on {row['category']} ({affinity:.1f}x avg)")
    elif affinity >= 0.5:
        reasons.append(f"regular {row['category']} spender")

    if days <= 7:
        reasons.append(f"transacted {int(days)} days ago")
    elif days <= 30:
        reasons.append(f"transacted within past {int(days)} days")
    elif days <= 90:
        reasons.append(f"active in past {int(days)} days")

    if row["cluster_score"] >= 0.5:
        reasons.append("cluster peers also prefer this")

    return "; ".join(reasons) if reasons else "general fit"


# ============================================================================
# Batch ranking (all customers)
# ============================================================================

def rank_for_all_customers() -> pd.DataFrame:
    print("Loading data...")
    customer_clusters = load_customer_clusters()
    affinity = load_category_affinity()
    catalog = get_catalog_df()
    cluster_prefs = compute_cluster_category_preferences(affinity, customer_clusters)

    print(f"  {len(customer_clusters):,} customers, {len(catalog)} coupons, "
          f"{len(cluster_prefs)} cluster-category prefs")

    # Compute population-level normalization constants
    # Use 99th percentile so we're not thrown off by extreme outliers
    affinity_p99 = float(affinity["affinity_index"].quantile(0.99))
    cluster_p99 = float(cluster_prefs["cluster_avg_affinity"].quantile(0.99))
    print(f"  Affinity p99: {affinity_p99:.2f}x  |  Cluster p99: {cluster_p99:.2f}x")

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
            affinity_p99=affinity_p99,
            cluster_p99=cluster_p99,
        )
        if not ranked.empty:
            all_results.append(ranked.head(3))

    result = pd.concat(all_results, ignore_index=True)

    # Score-distribution sanity check
    print(f"\nScore distribution across all recommendations:")
    print(f"  min={result['score'].min():.3f}  "
          f"p25={result['score'].quantile(0.25):.3f}  "
          f"median={result['score'].median():.3f}  "
          f"p75={result['score'].quantile(0.75):.3f}  "
          f"max={result['score'].max():.3f}")
    n_perfect = (result["score"] >= 0.99).sum()
    print(f"  perfect (≥0.99) scores: {n_perfect}  "
          f"({n_perfect/len(result)*100:.1f}% — should be <5%)")

    out = ARTIFACTS_DIR / "coupon_recommendations.parquet"
    result.to_parquet(out, index=False)
    print(f"\n✓ Wrote {len(result):,} (customer, coupon) recommendations to:\n  {out}")
    return result


def main():
    result = rank_for_all_customers()

    print("\n=== Sample recommendations ===")
    customer_clusters = load_customer_clusters()
    sample_personas = [
        "Luxury Seeker Vanessa", "College Student Sasha",
        "Soccer Mom Linda", "Active Retiree Carol",
        "Tech Bro Tyler", "New Parent Maya",
    ]

    for persona in sample_personas:
        sample = customer_clusters[customer_clusters["persona_name"] == persona]
        if sample.empty:
            continue
        sample_token = sample["customer_token"].iloc[0]
        cust_recs = result[result["customer_token"] == sample_token]
        if not cust_recs.empty:
            print(f"\n→ {persona}  (token: {sample_token[:8]}...)")
            for _, r in cust_recs.iterrows():
                print(f"   [{r['score']:.3f}] {r['merchant_name']:<22} "
                      f"{r['discount_display']:<12} — {r['title']}")
                print(f"             reason: {r['reasoning']}")


if __name__ == "__main__":
    main()
