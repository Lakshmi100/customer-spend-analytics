"""
Feature engineering for customer segmentation and coupon ranking.

Pulls from Snowflake MARTS.CUSTOMER_360 and produces:
    - feature_matrix: scaled numeric features for KMeans
    - feature_names:  the columns used (for interpretation later)
    - customer_index: customer_token in same row order as feature_matrix

Saves all artifacts to ml/artifacts/ so segmentation.py and predict.py
can reuse without re-querying Snowflake.

Why we separate this from segmentation.py:
- Single source of feature definitions = consistent train/inference
- Easy to swap in different scaling strategies
- Makes the feature engineering testable in isolation

Run from project root:
    python -m ml.features
"""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from ml.snowflake_io import query_snowflake

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
ARTIFACTS_DIR.mkdir(exist_ok=True)

# Numeric features for clustering. Curated subset of the 50 columns in
# customer_360 — picked because they capture *behavioral* signal that the
# model can learn from. We avoid:
#   - Identifiers (customer_token, persona_id) - leakage
#   - Categorical strings (state, family_status) - need separate encoding
#   - Highly correlated pairs (online_share + in_store_share = 1)
NUMERIC_FEATURES = [
    # Tenure
    "account_tenure_days",

    # RFM
    "recency_days",
    "frequency_total",
    "frequency_per_month",
    "monetary_total",
    "monetary_avg_txn",
    "monetary_per_month",

    # Spend profile
    "total_transactions",
    "total_spend",
    "avg_transaction_amount",
    "max_transaction_amount",
    "stddev_transaction_amount",
    "distinct_categories",
    "distinct_merchants",
    "active_months",
    "active_days",

    # Behavioral mix (shares, 0-1 range — already comparable but we still scale)
    "online_spend_share",
    "weekend_spend_share",
    "recurring_spend_share",
    "home_state_spend_share",
    "credit_spend_share",

    # Top-category concentration
    "top_category_1_share",
    "top_category_2_share",
    "top_category_3_share",
]


# Columns kept for INTERPRETATION / INFERENCE but NOT used as model features
META_COLUMNS = [
    "customer_token",
    "persona_id",
    "persona_name",
    "age_band",
    "income_band",
    "family_status",
    "top_category_1",
    "top_category_2",
    "top_category_3",
]


def load_customer_features() -> pd.DataFrame:
    """Pull customer_360 from Snowflake."""
    print("Loading customer_360 from Snowflake...")
    sql = f"""
        SELECT
            {', '.join(META_COLUMNS + NUMERIC_FEATURES)}
        FROM MARTS.CUSTOMER_360
    """
    df = query_snowflake(sql)
    print(f"  Loaded {len(df):,} customers, {df.shape[1]} columns")
    return df


def clean_features(df: pd.DataFrame) -> pd.DataFrame:
    """Handle nulls and infinities before scaling."""
    print("\nCleaning features...")
    initial_rows = len(df)

    # Replace +/- infinity with NaN, then fill NaN with 0
    # (NaN happens when a customer has 0 transactions — division produces NaN)
    df[NUMERIC_FEATURES] = (
        df[NUMERIC_FEATURES]
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0)
    )

    # Sanity check — no nulls remain
    null_count = df[NUMERIC_FEATURES].isnull().sum().sum()
    assert null_count == 0, f"Still have {null_count} nulls after cleaning"

    print(f"  ✓ {initial_rows:,} customers retained, 0 nulls remaining")
    return df


def build_feature_matrix(df: pd.DataFrame) -> tuple:
    """Scale numeric features and return (matrix, scaler, feature_names)."""
    print("\nScaling features (StandardScaler: zero mean, unit variance)...")
    X = df[NUMERIC_FEATURES].values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    print(f"  Feature matrix shape: {X_scaled.shape}")
    print(f"  Mean of scaled features (should be ~0): {X_scaled.mean():.6f}")
    print(f"  Std of scaled features  (should be ~1): {X_scaled.std():.6f}")
    return X_scaled, scaler


def main():
    df = load_customer_features()
    df = clean_features(df)
    X_scaled, scaler = build_feature_matrix(df)

    # Save artifacts so segmentation/inference can reuse without re-querying
    joblib.dump(scaler, ARTIFACTS_DIR / "scaler.joblib")
    np.save(ARTIFACTS_DIR / "X_scaled.npy", X_scaled)
    df[META_COLUMNS].to_parquet(ARTIFACTS_DIR / "customer_meta.parquet", index=False)

    # Save feature names so we can interpret cluster centroids later
    with open(ARTIFACTS_DIR / "feature_names.txt", "w") as f:
        f.write("\n".join(NUMERIC_FEATURES))

    print(f"\n✓ Saved artifacts to {ARTIFACTS_DIR}/")
    print(f"  - scaler.joblib")
    print(f"  - X_scaled.npy           ({X_scaled.shape})")
    print(f"  - customer_meta.parquet  ({len(df)} rows)")
    print(f"  - feature_names.txt      ({len(NUMERIC_FEATURES)} features)")

    # Print sample for sanity
    print(f"\nFirst 3 customers (meta only):")
    print(df[["customer_token", "persona_name", "top_category_1"]].head(3).to_string())


if __name__ == "__main__":
    main()
