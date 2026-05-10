"""
Snowflake loader: processed parquet -> Snowflake RAW tables.

Workflow:
    1. PUT processed parquet files into internal stage (each partition under a unique prefix)
    2. COPY INTO from stage into RAW tables with FORCE=TRUE (re-load if previously loaded)
    3. Validate row counts against actual file row counts (not just COPY output)
    4. Print summary

Run:
    python ingestion/snowflake_loader.py
"""

import glob
import os
import re
import sys
from pathlib import Path

import pyarrow.parquet as pq
import snowflake.connector
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

DB = "ABC_BANK_ANALYTICS"
SCHEMA = "RAW"
STAGE = f"{DB}.{SCHEMA}.INGESTION_STAGE"


def get_connection():
    return snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
        role=os.getenv("SNOWFLAKE_ROLE"),
        database=DB,
        schema=SCHEMA,
    )


def get_parquet_files(table_dir: Path) -> list:
    """Recursively find all .parquet files (handles partitioned dirs)."""
    return sorted(glob.glob(str(table_dir / "**" / "*.parquet"), recursive=True))


def count_rows_in_files(files: list) -> int:
    """Read the actual row count across all parquet files (truth source)."""
    total = 0
    for f in files:
        total += pq.read_metadata(f).num_rows
    return total


def stage_subpath_for_file(filepath: str, table_name: str) -> str:
    """
    Generate a unique stage subpath for each file so partitioned files don't collide.

    Spark writes:  data/processed/transactions/year_month=2024-03/part-00000-xxx.parquet
    We stage as:   @stage/transactions/year_month=2024-03/  (and PUT auto-uploads file)
    """
    p = Path(filepath)
    # Find the partition dir if it exists (e.g., year_month=2024-03)
    partition_part = ""
    for parent in p.parents:
        if "=" in parent.name:
            partition_part = f"{parent.name}/"
            break
    return f"{table_name}/{partition_part}"


def clear_stage(cursor, table_name: str) -> None:
    """Remove any previously staged files for this table to avoid stale state."""
    print(f"  Clearing stage @{STAGE}/{table_name}/")
    cursor.execute(f"REMOVE @{STAGE}/{table_name}/")


def upload_to_stage(cursor, files: list, table_name: str) -> None:
    """PUT each file into a unique sub-prefix in the stage so partitioned files don't collide."""
    print(f"  Uploading {len(files)} file(s) to stage @{STAGE}/{table_name}/")
    for filepath in files:
        subpath = stage_subpath_for_file(filepath, table_name)
        cursor.execute(
            f"PUT 'file://{filepath}' @{STAGE}/{subpath} "
            f"AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
        )
    print(f"  ✓ Upload complete")


def copy_into(cursor, table_name: str, columns: list) -> int:
    """
    COPY INTO the table from staged parquet.
    FORCE=TRUE means files will be reloaded even if Snowflake's load history has them.
    """
    col_list = ",\n            ".join(columns)
    select_list = ",\n            ".join(
        f"$1:{c}::{_col_type(c)}" for c in columns
    )
    sql = f"""
    COPY INTO {DB}.{SCHEMA}.{table_name.upper()} (
            {col_list}
        )
        FROM (
            SELECT
            {select_list}
            FROM @{STAGE}/{table_name}/
        )
        FILE_FORMAT = (FORMAT_NAME = '{DB}.{SCHEMA}.PARQUET_FORMAT')
        ON_ERROR = 'ABORT_STATEMENT'
        PURGE = FALSE
        FORCE = TRUE
    """
    print(f"  COPY INTO {table_name.upper()}...")
    cursor.execute(sql)
    result = cursor.fetchall()

    files_loaded = sum(1 for row in result if row[1] == "LOADED")
    files_skipped = sum(1 for row in result if row[1] != "LOADED")
    total_loaded = sum(row[3] for row in result if row[1] == "LOADED")
    total_errors = sum(row[5] for row in result if len(row) > 5 and row[5])

    print(f"  ✓ Files loaded: {files_loaded}, files skipped: {files_skipped}")
    print(f"  ✓ Rows loaded:  {total_loaded:,}, errors: {total_errors}")

    if files_skipped > 0:
        print(f"  ⚠ {files_skipped} files were skipped — check stage contents")

    return total_loaded


def _col_type(col_name: str) -> str:
    int_cols = {"num_dependents", "transaction_year", "transaction_month"}
    bool_cols = {"is_active", "is_recurring"}
    date_cols = {"account_open_date", "transaction_date"}
    ts_cols = {"created_at", "ingested_at", "transaction_ts"}
    float_cols = {"amount"}

    if col_name in int_cols:
        return "INTEGER"
    if col_name in bool_cols:
        return "BOOLEAN"
    if col_name in date_cols:
        return "DATE"
    if col_name in ts_cols:
        return "TIMESTAMP_NTZ"
    if col_name in float_cols:
        return "FLOAT"
    return "STRING"


CUSTOMER_COLUMNS = [
    "customer_id", "customer_token", "account_token",
    "persona_id", "persona_name",
    "age_band", "income_band", "household_income_band",
    "family_status", "num_dependents", "geography", "state", "zip_prefix",
    "account_open_date", "account_type", "credit_score_band", "is_active",
    "created_at", "ingested_at", "batch_id", "source_file",
]

TRANSACTION_COLUMNS = [
    "transaction_id", "customer_id", "customer_token",
    "transaction_date", "transaction_ts", "amount",
    "category", "merchant_id", "merchant_name", "channel",
    "payment_method", "is_recurring", "state", "txn_status",
    "year_month", "transaction_year", "transaction_month",
    "ingested_at", "batch_id", "source_file",
]


def truncate_table(cursor, table_name: str) -> None:
    cursor.execute(f"TRUNCATE TABLE IF EXISTS {DB}.{SCHEMA}.{table_name.upper()}")


def validate_counts(cursor, table_name: str, expected_from_files: int, loaded: int) -> None:
    cursor.execute(f"SELECT COUNT(*) FROM {DB}.{SCHEMA}.{table_name.upper()}")
    actual = cursor.fetchone()[0]
    print(f"\n  📊 Row count validation for {table_name.upper()}:")
    print(f"     Expected from parquet files: {expected_from_files:,}")
    print(f"     COPY reported loaded:        {loaded:,}")
    print(f"     Actual count in table:       {actual:,}")
    if actual == expected_from_files:
        print(f"     ✓ MATCH")
    else:
        delta = actual - expected_from_files
        print(f"     ✗ MISMATCH (delta: {delta:+,})")
        if delta < 0:
            print(f"     → Some files were not loaded. Check load_history below:")
            cursor.execute(f"""
                SELECT file_name, status, row_count, first_error_message
                FROM TABLE(INFORMATION_SCHEMA.COPY_HISTORY(
                    table_name=>'{DB}.{SCHEMA}.{table_name.upper()}',
                    start_time=>DATEADD(hours, -1, CURRENT_TIMESTAMP())
                ))
                ORDER BY last_load_time DESC
                LIMIT 30
            """)
            for row in cursor.fetchall():
                print(f"     {row}")


def main():
    customers_files = get_parquet_files(PROCESSED_DIR / "customers")
    transactions_files = get_parquet_files(PROCESSED_DIR / "transactions")

    if not customers_files:
        print(f"✗ No customer files found in {PROCESSED_DIR / 'customers'}")
        print("  Run python ingestion/spark_ingestion.py first")
        sys.exit(1)

    print(f"Found {len(customers_files)} customer file(s)")
    print(f"Found {len(transactions_files)} transaction file(s)")

    # Count actual rows in the parquet files (this is our source of truth)
    print("\nCounting rows in parquet files...")
    cust_expected = count_rows_in_files(customers_files)
    txn_expected = count_rows_in_files(transactions_files)
    print(f"  Customer files contain:    {cust_expected:,} rows")
    print(f"  Transaction files contain: {txn_expected:,} rows")

    print("\nConnecting to Snowflake...")
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # ---- Customers ----
        print("\n=== Loading CUSTOMERS ===")
        truncate_table(cursor, "customers")
        clear_stage(cursor, "customers")
        upload_to_stage(cursor, customers_files, "customers")
        cust_loaded = copy_into(cursor, "customers", CUSTOMER_COLUMNS)
        validate_counts(cursor, "customers", cust_expected, cust_loaded)

        # ---- Transactions ----
        print("\n=== Loading TRANSACTIONS ===")
        truncate_table(cursor, "transactions")
        clear_stage(cursor, "transactions")
        upload_to_stage(cursor, transactions_files, "transactions")
        txn_loaded = copy_into(cursor, "transactions", TRANSACTION_COLUMNS)
        validate_counts(cursor, "transactions", txn_expected, txn_loaded)

        print("\n" + "=" * 60)
        print("✓ Snowflake load complete!")
        print(f"  RAW.CUSTOMERS:    {cust_loaded:,} rows (expected {cust_expected:,})")
        print(f"  RAW.TRANSACTIONS: {txn_loaded:,} rows (expected {txn_expected:,})")
        print("=" * 60)
        print("\nVerify in Snowflake UI:")
        print(f"  USE DATABASE {DB};")
        print(f"  SELECT COUNT(*) FROM RAW.CUSTOMERS;")
        print(f"  SELECT COUNT(*) FROM RAW.TRANSACTIONS;")
        print(f"  SELECT category, COUNT(*) FROM RAW.TRANSACTIONS GROUP BY 1 ORDER BY 2 DESC;")

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()