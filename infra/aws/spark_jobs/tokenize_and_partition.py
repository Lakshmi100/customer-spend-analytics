"""
EMR Serverless Spark job: tokenize and partition.

Reads raw incoming data from S3, applies PII tokenization and k-anonymity,
writes tokenized parquet partitioned by year_month/day.

Same architecture works at portfolio scale (1.6M records) and at production
scale (100M records/day) — Spark auto-parallelizes based on input size.

SECURITY: This job enforces a trust boundary. Raw data arriving from the
upstream bank is NOT trusted to have tokenized correctly — we re-tokenize
with our own salt so we control the algorithm and can rotate the salt.
A fail-loud PII guard asserts no PII columns survive into the output.

INPUTS (S3):
    s3://<raw-bucket>/customers/ingest_date=YYYY-MM-DD/*.parquet
    s3://<raw-bucket>/transactions/ingest_date=YYYY-MM-DD/*.parquet

OUTPUTS (S3):
    s3://<processed-bucket>/customers/ingest_date=YYYY-MM-DD/*.parquet
    s3://<processed-bucket>/transactions/year_month=YYYY-MM/day=YYYY-MM-DD/*.parquet
"""

import argparse
import hashlib
import sys

import boto3
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StringType


# =============================================================================
# PII GUARD — the canonical list of columns that must NEVER reach the output.
#
# If any of these survive the transformation, the job CRASHES rather than
# silently writing PII to S3. For a tokenization pipeline, a loud crash is
# infinitely safer than a silent leak.
# =============================================================================

# Raw PII columns that must NEVER reach the output.
# NOTE: customer_token / account_token are NOT here — they are our
# privacy-preserving OUTPUT columns (the salted replacements for the
# raw IDs), re-computed inside transform_customers. They are the
# intended product of tokenization, not PII.
CUSTOMER_PII_COLUMNS = {
    "customer_id", "account_number",   # raw identifiers
    "first_name", "last_name", "full_name",
    "email", "phone_number",
    "date_of_birth", "street_address",
    "age", "annual_income", "household_income", "zip_code",
}

# customer_token is NOT PII — it's the re-computed safe output column.
TRANSACTION_PII_COLUMNS = {
    "customer_id",        # raw identifier (→ replaced by token)
}


# =============================================================================
# Configuration parsing
# =============================================================================

def parse_args():
    parser = argparse.ArgumentParser(description="Tokenize and partition raw data")
    parser.add_argument("--raw-bucket", required=True)
    parser.add_argument("--processed-bucket", required=True)
    parser.add_argument("--pii-salt-secret-arn", required=True)
    parser.add_argument("--ingest-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--region", default="us-east-1")
    return parser.parse_args()


# =============================================================================
# Secrets Manager
# =============================================================================

def fetch_pii_salt(secret_arn: str, region: str) -> str:
    client = boto3.client("secretsmanager", region_name=region)
    return client.get_secret_value(SecretId=secret_arn)["SecretString"]


# =============================================================================
# Tokenization UDF
# =============================================================================

def make_tokenize_udf(salt: str):
    def tokenize(value):
        if value is None:
            return None
        h = hashlib.sha256()
        h.update(salt.encode("utf-8"))
        h.update(str(value).encode("utf-8"))
        return h.hexdigest()[:16]
    return F.udf(tokenize, StringType())


# =============================================================================
# K-anonymity transformations
# =============================================================================

def age_band(col):
    return (F.when(col < 25, "18-24")
             .when(col < 35, "25-34")
             .when(col < 45, "35-44")
             .when(col < 55, "45-54")
             .when(col < 65, "55-64")
             .otherwise("65+"))


def income_band(col):
    return (F.when(col < 40000,  "under_40k")
             .when(col < 75000,  "40k_75k")
             .when(col < 125000, "75k_125k")
             .when(col < 200000, "125k_200k")
             .otherwise("over_200k"))


def zip_prefix(col):
    return F.concat(F.substring(col, 1, 3), F.lit("XX"))


# =============================================================================
# PII guard — fail loudly if any PII column survived
# =============================================================================

def assert_no_pii(df, pii_columns, label):
    leaked = pii_columns & set(df.columns)
    if leaked:
        raise ValueError(
            f"PII GUARD FAILED for {label}: these PII columns were NOT "
            f"stripped and would have been written to S3: {sorted(leaked)}. "
            f"Aborting job to prevent a PII leak."
        )
    print(f"  ✓ PII guard passed for {label} — no PII columns in output")


# =============================================================================
# Customer transformation
# =============================================================================

def transform_customers(df, tokenize_udf):
    """
    Tokenize + k-anonymize customers.

    Re-tokenizes from customer_id with OUR salt (trust boundary): the upstream
    customer_token is dropped and recomputed, so we control the algorithm.

    Drops every column in CUSTOMER_PII_COLUMNS. Bands age, annual_income,
    household_income, and zip_code into k-anonymous ranges.
    """
    out = (df
        # Re-tokenize with our salt — overwrites any upstream customer_token
        .withColumn("customer_token", tokenize_udf(F.col("customer_id")))
        .withColumn("account_token",  tokenize_udf(F.col("account_number")))

        # K-anonymity bands
        .withColumn("age_band",              age_band(F.col("age")))
        .withColumn("income_band",           income_band(F.col("annual_income")))
        .withColumn("household_income_band", income_band(F.col("household_income")))
        .withColumn("zip_prefix",            zip_prefix(F.col("zip_code")))

        # Drop ALL raw PII — explicit list matching the real schema.
        # customer_token/account_token survive because they were re-created
        # ABOVE as new columns; .drop() removes the ORIGINAL same-named column
        # only if it still exists — so we drop by the raw-PII names only.
        .drop("customer_id", "account_number",
              "first_name", "last_name", "full_name",
              "email", "phone_number",
              "date_of_birth", "street_address",
              "age", "annual_income", "household_income", "zip_code")
    )

    # Fail loudly if anything PII slipped through
    assert_no_pii(out, CUSTOMER_PII_COLUMNS, "customers")
    return out


# =============================================================================
# Transaction transformation
# =============================================================================

def transform_transactions(df, tokenize_udf):
    """
    Re-tokenize customer reference + add partition columns.

    Accepts TWO schemas to support multiple upstream producers:
      - Raw schema (local generator): has `customer_id`, no `customer_token`
        → tokenize customer_id with our salt
      - Delta schema (Lambda generator): already has `customer_token`
        → trust it (came from our own Snowflake which holds our salted tokens)

    transaction_ts (timestamp) is NOT PII — kept as-is.
    """
    cols = set(df.columns)

    if "customer_id" in cols:
        # Raw producer: tokenize fresh
        out = (df
            .withColumn("customer_token", tokenize_udf(F.col("customer_id")))
            .drop("customer_id")
        )
    elif "customer_token" in cols:
        # Delta producer: already tokenized via our Snowflake lookup
        out = df
    else:
        raise ValueError(
            "Transactions input must contain 'customer_id' or 'customer_token'. "
            f"Got columns: {sorted(cols)}"
        )

    # Add partition columns regardless of producer
    out = (out
        .withColumn("year_month", F.date_format(F.col("transaction_date"), "yyyy-MM"))
        .withColumn("day",        F.date_format(F.col("transaction_date"), "yyyy-MM-dd"))
    )

    assert_no_pii(out, TRANSACTION_PII_COLUMNS, "transactions")
    return out


# =============================================================================
# Main
# =============================================================================

def main():
    args = parse_args()

    print("━" * 63)
    print("  Spark job: tokenize_and_partition")
    print(f"  Raw bucket:        {args.raw_bucket}")
    print(f"  Processed bucket:  {args.processed_bucket}")
    print(f"  Ingest date:       {args.ingest_date}")
    print(f"  Region:            {args.region}")
    print("━" * 63)

    print("→ Fetching PII salt from Secrets Manager...")
    salt = fetch_pii_salt(args.pii_salt_secret_arn, args.region)
    print(f"  ✓ Salt fetched (length: {len(salt)} chars)")

    spark = (SparkSession.builder
        .appName("tokenize_and_partition")
        .config("spark.sql.parquet.compression.codec", "snappy")
        .config("spark.sql.sources.partitionOverwriteMode", "dynamic")
        .config("spark.hadoop.fs.s3a.connection.maximum", "200")
        .config("spark.hadoop.fs.s3a.fast.upload", "true")
        .getOrCreate()
    )

    tokenize_udf = make_tokenize_udf(salt)

    # ----- Customers -----
    print(f"\n→ Reading customers from s3://{args.raw_bucket}/customers/ingest_date={args.ingest_date}/")
    customers_input = f"s3a://{args.raw_bucket}/customers/ingest_date={args.ingest_date}/"
    try:
        customers_raw = spark.read.parquet(customers_input)
        customer_count = customers_raw.count()
        print(f"  ✓ Read {customer_count:,} customer rows")
    except Exception as e:
        print(f"  ⚠ No customers found at this path: {e}")
        customer_count = 0

    if customer_count > 0:
        customers_out = transform_customers(customers_raw, tokenize_udf)
        customers_output = f"s3a://{args.processed_bucket}/customers/ingest_date={args.ingest_date}/"
        print(f"→ Writing tokenized customers to {customers_output}")
        customers_out.write.mode("overwrite").parquet(customers_output)
        print(f"  ✓ Wrote {customer_count:,} tokenized customer rows")

    # ----- Transactions -----
    print(f"\n→ Reading transactions from s3://{args.raw_bucket}/transactions/ingest_date={args.ingest_date}/")
    transactions_input = f"s3a://{args.raw_bucket}/transactions/ingest_date={args.ingest_date}/"
    try:
        transactions_raw = spark.read.parquet(transactions_input)
        transaction_count = transactions_raw.count()
        print(f"  ✓ Read {transaction_count:,} transaction rows")
    except Exception as e:
        print(f"  ⚠ No transactions found at this path: {e}")
        transaction_count = 0

    if transaction_count > 0:
        transactions_out = transform_transactions(transactions_raw, tokenize_udf)
        transactions_output = f"s3a://{args.processed_bucket}/transactions/"
        print(f"→ Writing tokenized transactions to {transactions_output}")
        print(f"  (partitioned by year_month/day, dynamic overwrite — idempotent)")
        (transactions_out
            .write
            .partitionBy("year_month", "day")
            .mode("overwrite")
            .parquet(transactions_output))
        print(f"  ✓ Wrote {transaction_count:,} tokenized transaction rows")

    # ----- Fail loudly if BOTH inputs were empty (likely a config error) -----
    if customer_count == 0 and transaction_count == 0:
        raise ValueError(
            f"Job processed ZERO rows for ingest-date {args.ingest_date}. "
            f"This usually means the --ingest-date does not match any raw data "
            f"partition. Check s3://{args.raw_bucket}/ for available dates. "
            f"Failing the job rather than reporting a misleading SUCCESS."
        )

    print("\n" + "━" * 63)
    print("  ✓ Job complete")
    print(f"  Customers processed:    {customer_count:,}")
    print(f"  Transactions processed: {transaction_count:,}")
    print("━" * 63)

    spark.stop()


if __name__ == "__main__":
    main()
