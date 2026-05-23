"""
snowflake_loader Lambda.

Triggered by Step Functions (or direct invocation for testing). Loads
EMR-tokenized data from S3 into Snowflake RAW tables via COPY INTO
through the storage integration handshake.

Idempotent: every invocation TRUNCATEs then COPYs, so running twice
produces the same final state. Same input -> same output.

Trade-off documented: concurrent invocations would race each other on
TRUNCATE. Safe for the Step Functions daily schedule (one at a time);
not safe for parallel fan-out. Acceptable for our use case.

INPUT (event):
    {
        "ingest_date": "2026-05-15"   # optional - used for customers path
    }
    If ingest_date is omitted, defaults to today's date.

OUTPUT:
    {
        "status": "success",
        "ingest_date": "2026-05-15",
        "customers_loaded": 1000,
        "transactions_loaded": 1621434,
        "transactions_distinct_days": 760
    }

CONFIGURATION (environment variables, set by Terraform):
    SNOWFLAKE_SECRET_ARN     - ARN of Secrets Manager secret with Snowflake creds
    SNOWFLAKE_DATABASE       - e.g., ABC_BANK_ANALYTICS
    SNOWFLAKE_SCHEMA         - e.g., RAW
    SNOWFLAKE_WAREHOUSE      - e.g., COMPUTE_WH
    SNOWFLAKE_ROLE           - e.g., ACCOUNTADMIN
    STAGE_NAME               - e.g., csa_processed_stage
    AWS_REGION_OVERRIDE      - optional, defaults to Lambda's region
"""

import json
import logging
import os
from datetime import date

import boto3
import snowflake.connector

logger = logging.getLogger()
logger.setLevel(logging.INFO)


# =============================================================================
# Secrets Manager
# =============================================================================

def fetch_snowflake_credentials(secret_arn: str, region: str) -> dict:
    """
    Read Snowflake credentials from Secrets Manager.

    Secret is expected to be a JSON string with keys:
        account, user, password
    """
    client = boto3.client("secretsmanager", region_name=region)
    response = client.get_secret_value(SecretId=secret_arn)
    creds = json.loads(response["SecretString"])

    required = {"account", "user", "password"}
    missing = required - set(creds.keys())
    if missing:
        raise ValueError(
            f"Snowflake secret missing required keys: {sorted(missing)}"
        )
    return creds


# =============================================================================
# Snowflake connection
# =============================================================================

def open_snowflake_connection(creds: dict):
    """Open a Snowflake connection with the configured warehouse/database/role."""
    return snowflake.connector.connect(
        account=creds["account"],
        user=creds["user"],
        password=creds["password"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=os.environ["SNOWFLAKE_SCHEMA"],
        role=os.environ["SNOWFLAKE_ROLE"],
        # Network resilience for Lambda's flaky cold-network environment
        network_timeout=60,
        login_timeout=30,
    )


# =============================================================================
# Load logic
# =============================================================================

def load_customers(cursor, ingest_date: str, stage_name: str) -> int:
    """
    TRUNCATE then COPY INTO customers. Returns row count loaded.

    Uses MATCH_BY_COLUMN_NAME because customer parquet schema matches
    RAW.CUSTOMERS column-for-column — no path extraction needed for
    customer data (it's not Hive-partitioned, just a flat ingest_date prefix).
    """
    logger.info(f"Truncating RAW.CUSTOMERS...")
    cursor.execute("TRUNCATE TABLE RAW.CUSTOMERS")

    copy_sql = f"""
        COPY INTO RAW.CUSTOMERS
        FROM @{stage_name}/customers/ingest_date={ingest_date}/
        FILE_FORMAT = (TYPE = PARQUET)
        MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
        PATTERN = '.*[.]parquet'
        ON_ERROR = ABORT_STATEMENT
    """
    logger.info(f"Loading customers from ingest_date={ingest_date}...")
    cursor.execute(copy_sql)

    cursor.execute("SELECT COUNT(*) FROM RAW.CUSTOMERS")
    count = cursor.fetchone()[0]
    logger.info(f"  Loaded {count:,} customer rows")
    return count


def load_transactions(cursor, stage_name: str) -> tuple:
    """
    TRUNCATE then COPY INTO transactions with path extraction for
    year_month and day partition columns.

    Returns (total_rows, distinct_days).

    Uses explicit column-by-column projection (not MATCH_BY_COLUMN_NAME)
    because we need REGEXP_SUBSTR(METADATA$FILENAME, ...) to reconstruct
    year_month and day from the Hive-style folder paths — Spark doesn't
    write partition columns into parquet content, only into folder names.
    """
    logger.info(f"Truncating RAW.TRANSACTIONS...")
    cursor.execute("TRUNCATE TABLE RAW.TRANSACTIONS")

    copy_sql = f"""
        COPY INTO RAW.TRANSACTIONS (
            transaction_id, customer_token, transaction_date, transaction_ts,
            amount, category, merchant_id, merchant_name, channel,
            payment_method, is_recurring, state, txn_status,
            year_month, day
        )
        FROM (
            SELECT
                $1:transaction_id::VARCHAR,
                $1:customer_token::VARCHAR,
                $1:transaction_date::DATE,
                $1:transaction_ts::TIMESTAMP_NTZ,
                $1:amount::FLOAT,
                $1:category::VARCHAR,
                $1:merchant_id::VARCHAR,
                $1:merchant_name::VARCHAR,
                $1:channel::VARCHAR,
                $1:payment_method::VARCHAR,
                $1:is_recurring::BOOLEAN,
                $1:state::VARCHAR,
                $1:txn_status::VARCHAR,
                REGEXP_SUBSTR(METADATA$FILENAME, 'year_month=([^/]+)', 1, 1, 'e', 1)::VARCHAR AS year_month,
                REGEXP_SUBSTR(METADATA$FILENAME, 'day=([^/]+)', 1, 1, 'e', 1)::VARCHAR        AS day
            FROM @{stage_name}/transactions/
        )
        FILE_FORMAT = (TYPE = PARQUET)
        PATTERN = '.*[.]parquet'
        ON_ERROR = ABORT_STATEMENT
    """
    logger.info("Loading transactions (path-extraction for year_month + day)...")
    cursor.execute(copy_sql)

    cursor.execute("""
        SELECT COUNT(*), COUNT(DISTINCT day), COUNT(*) - COUNT(day)
        FROM RAW.TRANSACTIONS
    """)
    total, distinct_days, null_days = cursor.fetchone()
    logger.info(f"  Loaded {total:,} transaction rows across {distinct_days} days")

    # Fail-loud guard: same pattern as the Spark PII guard.
    # NULL partition columns silently break downstream date-based analytics.
    if null_days > 0:
        raise ValueError(
            f"DATA QUALITY FAILURE: {null_days:,} of {total:,} transaction rows "
            f"have NULL day. Path extraction REGEX must have failed on some files. "
            f"Aborting to prevent silent downstream corruption."
        )

    return total, distinct_days


# =============================================================================
# Lambda entry point
# =============================================================================

def lambda_handler(event, context):
    """
    Triggered by Step Functions or direct invocation.

    event: {"ingest_date": "YYYY-MM-DD"}  (optional, defaults to today)
    """
    region = os.environ.get("AWS_REGION_OVERRIDE", os.environ.get("AWS_REGION", "us-east-1"))
    secret_arn = os.environ["SNOWFLAKE_SECRET_ARN"]
    stage_name = os.environ["STAGE_NAME"]

    # Default ingest_date to today (UTC) if not supplied
    ingest_date = event.get("ingest_date") or date.today().isoformat()
    logger.info(f"Starting load for ingest_date={ingest_date}")

    # 1) Fetch credentials
    creds = fetch_snowflake_credentials(secret_arn, region)
    logger.info(f"Fetched Snowflake credentials for account: {creds['account']}")

    # 2) Connect and load
    conn = open_snowflake_connection(creds)
    try:
        cursor = conn.cursor()
        try:
            customers_count = load_customers(cursor, ingest_date, stage_name)
            transactions_total, transactions_days = load_transactions(cursor, stage_name)
        finally:
            cursor.close()
    finally:
        conn.close()

    result = {
        "status": "success",
        "ingest_date": ingest_date,
        "customers_loaded": customers_count,
        "transactions_loaded": transactions_total,
        "transactions_distinct_days": transactions_days,
    }
    logger.info(f"Load complete: {result}")
    return result
