"""
Inference API for the coupon recommender.

This is the production interface — what FastAPI will eventually call.
Given a customer_token, returns top N coupons with reasoning.

Usage as a module:
    from ml.predict import get_coupons
    recs = get_coupons("7c4ba8bb6ad29427", top_n=3)
    for r in recs:
        print(r["merchant_name"], r["title"], r["score"])

Usage as CLI:
    python -m ml.predict 7c4ba8bb6ad29427
    python -m ml.predict 7c4ba8bb6ad29427 --top-n 5
"""

import argparse
import json
from functools import lru_cache
from pathlib import Path
from typing import List, Dict

import pandas as pd

from ml.coupon_catalog import get_catalog_df
from ml.coupon_ranker import (
    compute_cluster_category_preferences,
    load_category_affinity,
    load_customer_clusters,
    score_coupons_for_customer,
)

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"


# Cache the full data load so repeated lookups in the same Python session are instant.
# In FastAPI we'd refresh this on a schedule rather than cache forever.
@lru_cache(maxsize=1)
def _load_lookup_data():
    customer_clusters = load_customer_clusters()
    affinity = load_category_affinity()
    catalog = get_catalog_df()
    cluster_prefs = compute_cluster_category_preferences(affinity, customer_clusters)
    return customer_clusters, affinity, catalog, cluster_prefs


def get_coupons(customer_token: str, top_n: int = 3) -> List[Dict]:
    """
    Return top N coupon recommendations for a customer.

    Args:
        customer_token: customer's analytics-safe token (from CUSTOMER_360)
        top_n: how many coupons to return (default 3)

    Returns:
        List of dicts with: coupon_id, merchant_name, category, title,
        discount_display, score, reasoning, and signal components.

    Raises:
        ValueError: if customer_token not found in the cluster assignments.
    """
    customer_clusters, affinity, catalog, cluster_prefs = _load_lookup_data()

    # Look up the customer
    cust_row = customer_clusters[customer_clusters["customer_token"] == customer_token]
    if cust_row.empty:
        raise ValueError(
            f"Customer {customer_token} not found in cluster assignments. "
            f"Run `python -m ml.segmentation` first."
        )
    customer_cluster = int(cust_row["cluster"].iloc[0])
    persona_name = cust_row["persona_name"].iloc[0]

    # Get this customer's affinity rows
    cust_aff = affinity[affinity["customer_token"] == customer_token]

    # Score
    ranked = score_coupons_for_customer(
        customer_token=customer_token,
        catalog=catalog,
        customer_affinity=cust_aff,
        cluster_prefs=cluster_prefs,
        customer_cluster=customer_cluster,
    )

    # Build response
    top = ranked.head(top_n)
    output = []
    for _, r in top.iterrows():
        output.append({
            "coupon_id": r["coupon_id"],
            "merchant_name": r["merchant_name"],
            "category": r["category"],
            "tier": r["tier"],
            "title": r["title"],
            "discount_display": r["discount_display"],
            "score": round(float(r["score"]), 4),
            "components": {
                "affinity_score": round(float(r["affinity_score"]), 4),
                "recency_score": round(float(r["recency_score"]), 4),
                "cluster_score": round(float(r["cluster_score"]), 4),
            },
            "signals": {
                "affinity_index": round(float(r["affinity_index"]), 2),
                "days_since_last_txn": int(r["days_since_last_txn"]),
                "wallet_share": round(float(r["spend_share"]), 4),
            },
            "reasoning": r["reasoning"],
            "_meta": {
                "customer_cluster": customer_cluster,
                "customer_persona": persona_name,
            },
        })
    return output


def cli():
    parser = argparse.ArgumentParser(description="Get coupon recommendations for a customer")
    parser.add_argument("customer_token", help="Customer token from CUSTOMER_360")
    parser.add_argument("--top-n", type=int, default=3, help="Number of coupons (default 3)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    recs = get_coupons(args.customer_token, top_n=args.top_n)

    if args.json:
        print(json.dumps(recs, indent=2))
        return

    if not recs:
        print(f"No coupons matched for {args.customer_token}")
        return

    persona = recs[0]["_meta"]["customer_persona"]
    cluster = recs[0]["_meta"]["customer_cluster"]
    print(f"\n🎟  Coupon recommendations")
    print(f"   Customer: {args.customer_token}")
    print(f"   Persona:  {persona}  (cluster {cluster})")
    print(f"   {'-' * 60}")

    for i, r in enumerate(recs, 1):
        print(f"\n   {i}. [{r['score']:.3f}] {r['merchant_name']}  "
              f"({r['discount_display']}, {r['tier']})")
        print(f"      {r['title']}")
        print(f"      Why: {r['reasoning']}")
        print(f"      Signals — affinity: {r['signals']['affinity_index']:.1f}x, "
              f"last txn: {r['signals']['days_since_last_txn']} days ago, "
              f"wallet: {r['signals']['wallet_share']*100:.0f}%")


if __name__ == "__main__":
    cli()
