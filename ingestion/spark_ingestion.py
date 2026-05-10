"""
PySpark ingestion job: raw parquet -> tokenized, validated, processed parquet.

This is where the trust boundary lives. Raw data from ABC Bank arrives with
full PII. After this job, the analytics layer only sees tokens + bands —
never names, never emails, never DOB, never full zip codes.

Reads:
    data/raw/customers.parquet   (with PII)
    data/raw/transactions.parquet

Writes:
    data/processed/customers/        (PII stripped)
    data/processed/transactions/     (partitioned by year_month)

Run:
    python ingestion/spark_ingestion.py
"""

import sys
import uuid
import pii_tokenizer
from datetime import datetime
from pathlib import Path

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, DoubleType

sys.path.append(str(Path(__file__).parent))
from pii_tokenizer import (
    age_to_band, income_to_band, truncate_zip,
    PII_DROP_COLUMNS, PII_TOKENIZE_COLUMNS, tokenize,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def get_spark() -> SparkSession:
    session =  (
        SparkSession.builder
        .appName("ABC_Bank_Ingestion")
        .master("local[*]")
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.driver.memory", "4g")
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.parquet.compression.codec", "snappy")
        .config("spark.ui.showConsoleProgress", "false")
        .getOrCreate()
    )
    session.sparkContext.addPyFile(str(Path(__file__).parent / "pii_tokenizer.py"))
    return session


def ingest_customers(spark: SparkSession, batch_id: str) -> int:
    print("\n" + "=" * 70)
    print("INGESTING CUSTOMERS")
    print("=" * 70)

    raw_path = RAW_DIR / "customers.parquet"
    df = spark.read.parquet(str(raw_path))
    raw_count = df.count()
    raw_columns = set(df.columns)
    print(f"  Raw rows: {raw_count:,}")
    print(f"  Raw columns ({len(raw_columns)}): {sorted(raw_columns)}")

    # === Show what's about to be stripped ===
    pii_present = [c for c in df.columns if c.lower() in PII_DROP_COLUMNS]
    pii_to_tokenize = [c for c in df.columns if c.lower() in PII_TOKENIZE_COLUMNS]

    print(f"\n  🔒 PII columns to DROP: {pii_present}")
    print(f"  🔑 Columns to TOKENIZE:  {pii_to_tokenize}")

    print(f"\n  Sample of incoming PII (first 3 rows):")
    sample_pii_cols = [c for c in ["first_name", "last_name", "email",
                                    "phone_number", "date_of_birth",
                                    "street_address"] if c in df.columns]
    if sample_pii_cols:
        df.select(*sample_pii_cols).show(3, truncate=False)

    # === UDFs for transformations ===
    age_band_udf = F.udf(age_to_band, StringType())
    income_band_udf = F.udf(income_to_band, StringType())
    zip_truncate_udf = F.udf(truncate_zip, StringType())
    tokenize_udf = F.udf(tokenize, StringType())

    cleaned = (
        df
        # K-anonymization: replace exact age with age band
        .withColumn("age_band", age_band_udf(F.col("age")))
        .withColumn("income_band", income_band_udf(F.col("annual_income")))
        .withColumn("household_income_band", income_band_udf(F.col("household_income")))
        # K-anonymization: replace full zip with 3-digit prefix
        .withColumn("zip_prefix", zip_truncate_udf(F.col("zip_code")))
        # Tokenize account_number (still useful for joins, but now opaque)
        .withColumn("account_token", tokenize_udf(F.col("account_number")))
        # Ingestion metadata
        .withColumn("ingested_at", F.current_timestamp())
        .withColumn("batch_id", F.lit(batch_id))
        .withColumn("source_file", F.lit("customers.parquet"))
    )

    # === DROP all PII columns ===
    cols_to_drop = [c for c in cleaned.columns if c.lower() in PII_DROP_COLUMNS]
    cols_to_drop += ["age", "annual_income", "household_income", "zip_code", "account_number"]
    cleaned = cleaned.drop(*cols_to_drop)

    final_columns = set(cleaned.columns)
    print(f"\n  ✓ Stripped {len(cols_to_drop)} PII/raw columns")
    print(f"  ✓ Output columns ({len(final_columns)}): {sorted(final_columns)}")

    # === Validate: NO PII columns remain ===
    pii_leakage = [c for c in cleaned.columns if c.lower() in PII_DROP_COLUMNS]
    assert not pii_leakage, f"PII LEAKAGE DETECTED: {pii_leakage}"

    null_tokens = cleaned.filter(F.col("customer_token").isNull()).count()
    assert null_tokens == 0, f"{null_tokens} rows have null customer_token"

    # === Write ===
    out_path = PROCESSED_DIR / "customers"
    (
        cleaned
        .coalesce(1)
        .write
        .mode("overwrite")
        .parquet(str(out_path))
    )

    out_count = cleaned.count()
    print(f"\n  Processed rows: {out_count:,} → {out_path}")

    # === Show before/after diff ===
    print(f"\n  📊 BEFORE → AFTER ingestion:")
    print(f"     Columns: {len(raw_columns)} → {len(final_columns)}")
    print(f"     PII removed: {sorted(raw_columns - final_columns)}")
    print(f"     New analytics-safe columns: {sorted(final_columns - raw_columns)}")

    print(f"\n  Sample of processed data (first 3 rows):")
    safe_sample_cols = ["customer_token", "persona_name", "age_band",
                        "income_band", "state", "zip_prefix"]
    cleaned.select(*safe_sample_cols).show(3, truncate=False)

    assert raw_count == out_count, f"Row count mismatch: {raw_count} -> {out_count}"
    return out_count


def ingest_transactions(spark: SparkSession, batch_id: str) -> int:
    print("\n" + "=" * 70)
    print("INGESTING TRANSACTIONS")
    print("=" * 70)

    raw_path = RAW_DIR / "transactions.parquet"
    df = spark.read.parquet(str(raw_path))
    raw_count = df.count()
    print(f"  Raw rows: {raw_count:,}")

    cleaned = (
        df
        .withColumn("year_month", F.date_format(F.col("transaction_date"), "yyyy-MM"))
        .withColumn("transaction_year", F.year(F.col("transaction_date")))
        .withColumn("transaction_month", F.month(F.col("transaction_date")))
        .withColumn("amount", F.col("amount").cast(DoubleType()))
        .withColumn("ingested_at", F.current_timestamp())
        .withColumn("batch_id", F.lit(batch_id))
        .withColumn("source_file", F.lit("transactions.parquet"))
    )

    bad_amounts = cleaned.filter(F.col("amount") <= 0).count()
    assert bad_amounts == 0, f"{bad_amounts} transactions with non-positive amount"

    null_tokens = cleaned.filter(F.col("customer_token").isNull()).count()
    assert null_tokens == 0, f"{null_tokens} transactions with null customer_token"

    out_path = PROCESSED_DIR / "transactions"
    (
        cleaned
        .write
        .mode("overwrite")
        .partitionBy("year_month")
        .parquet(str(out_path))
    )

    out_count = cleaned.count()
    print(f"  Processed rows: {out_count:,} → {out_path}")

    print("  Partitions written:")
    cleaned.groupBy("year_month").count().orderBy("year_month").show(30, truncate=False)

    assert raw_count == out_count, f"Row count mismatch: {raw_count} -> {out_count}"
    return out_count


def main():
    batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    print(f"Starting ingestion batch: {batch_id}")

    spark = get_spark()
    spark.sparkContext.setLogLevel("WARN")

    try:
        cust_count = ingest_customers(spark, batch_id)
        txn_count = ingest_transactions(spark, batch_id)

        print("\n" + "=" * 70)
        print(f"✓ INGESTION COMPLETE")
        print("=" * 70)
        print(f"  Batch ID:       {batch_id}")
        print(f"  Customers:      {cust_count:,}  (PII stripped ✓)")
        print(f"  Transactions:   {txn_count:,}  (partitioned by year_month ✓)")
        print(f"  Trust boundary: enforced ✓")
        print("=" * 70)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()