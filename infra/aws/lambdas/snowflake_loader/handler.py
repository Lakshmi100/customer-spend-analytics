"""
snowflake_loader Lambda.

Triggered by Step Functions (or direct invocation for testing). Loads
EMR-tokenized data from S3 into Snowflake RAW tables via COPY INTO
through the storage integration handshake.

LOAD PATTERNS (different for each table by design):
  - CUSTOMERS  : MERGE (Type 1 SCD)
                 - Customers are slowly-changing dimensions; most days bring
                   zero new ones. Existing customers must be preserved.
                 - Pattern: COPY to temp staging table -> MERGE into main
                   on customer_token (insert new, update existing in place).
  - TRANSACTIONS : TRUNCATE + COPY (full reload)
                   - Transactions are append-only events; we re-COPY the full
                     S3 tree every run. Idempotent because the source data
                     is immutable on S3.

Same input -> same final state for both tables.

INPUT (event):
    { "ingest_date": "2026-05-15" }  # optional, defaults to today

OUTPUT:
    {
        "status": "success",
        "ingest_date": "2026-05-15",
        "customers_total": 1002,      # total in table after MERGE
        "customers_inserted": 2,      # new customers from today's delta
        "customers_updated": 0,       # existing customers re-uploaded
        "transactions_loaded": 1621474,
        "transactions_distinct_days": 761
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
    return snowflake.connector.connect(
        account=creds["account"],
        user=creds["user"],
        password=creds["password"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=os.environ["SNOWFLAKE_SCHEMA"],
        role=os.environ["SNOWFLAKE_ROLE"],
        network_timeout=60,
        login_timeout=30,
    )


# =============================================================================
# Customer load: MERGE pattern (Type 1 SCD)
# =============================================================================

def load_customers(cursor, ingest_date: str, stage_name: str) -> dict:
    """
    MERGE today's customer batch into RAW.CUSTOMERS, preserving prior days'
    customers.

    Three steps:
      1. CREATE OR REPLACE TEMP TABLE -- empty staging table with same shape
         as RAW.CUSTOMERS
      2. COPY INTO the staging table from S3
      3. MERGE staging into RAW.CUSTOMERS on customer_token

    The MERGE statement uses `WHEN MATCHED THEN UPDATE` for re-uploads of
    existing customers (their profile fields may have changed) and
    `WHEN NOT MATCHED THEN INSERT` for new customers.

    Returns counts: total, inserted, updated.
    """
    logger.info(f"Loading customers for ingest_date={ingest_date} (MERGE pattern)")

    # ---- Step 1: Create empty staging table with same shape as the target
    # CREATE OR REPLACE drops any prior temp table (safety if a previous
    # invocation crashed mid-load and somehow left state — though TEMP tables
    # auto-drop at session end, this is belt-and-suspenders).
    cursor.execute("""
        CREATE OR REPLACE TEMPORARY TABLE RAW.CUSTOMERS_STAGE
        LIKE RAW.CUSTOMERS
    """)

    # ---- Step 2: COPY today's S3 delta into the staging table
    copy_sql = f"""
        COPY INTO RAW.CUSTOMERS_STAGE
        FROM @{stage_name}/customers/ingest_date={ingest_date}/
        FILE_FORMAT = (TYPE = PARQUET)
        MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
        PATTERN = '.*[.]parquet'
        ON_ERROR = ABORT_STATEMENT
    """
    cursor.execute(copy_sql)
    cursor.execute("SELECT COUNT(*) FROM RAW.CUSTOMERS_STAGE")
    staged_count = cursor.fetchone()[0]
    logger.info(f"  Staged {staged_count:,} customer rows for MERGE")

    # ---- Step 3: MERGE staging into target. Type 1 SCD: keep latest version.
    #
    # We explicitly list the fields rather than using `UPDATE SET *` because
    # `UPDATE SET *` requires identical column orders + names in both tables,
    # which is fragile across schema changes. Explicit is safer.
    #
    # Note: we do NOT update customer_token in WHEN MATCHED. The token IS the
    # join key, so updating it would be either no-op or destructive.
    # Column names verified against DESCRIBE TABLE RAW.CUSTOMERS:
    #   CUSTOMER_TOKEN, ACCOUNT_TOKEN, PERSONA_ID, PERSONA_NAME, AGE_BAND,
    #   INCOME_BAND, HOUSEHOLD_INCOME_BAND, FAMILY_STATUS, NUM_DEPENDENTS,
    #   GEOGRAPHY, STATE, ZIP_PREFIX, ACCOUNT_OPEN_DATE, ACCOUNT_TYPE,
    #   CREDIT_SCORE_BAND, IS_ACTIVE, CREATED_AT,
    #   INGESTED_AT, BATCH_ID, SOURCE_FILE  (← metadata, handled separately)
    #
    # The three metadata columns (INGESTED_AT, BATCH_ID, SOURCE_FILE) are NOT
    # in the EMR parquet. On INSERT we stamp INGESTED_AT with the load time and
    # leave BATCH_ID/SOURCE_FILE NULL (could be wired later). On UPDATE we
    # refresh INGESTED_AT so we know when a record was last touched, but we do
    # NOT overwrite the data columns with anything the source lacks.
    merge_sql = """
        MERGE INTO RAW.CUSTOMERS AS target
        USING RAW.CUSTOMERS_STAGE AS source
            ON target.customer_token = source.customer_token

        WHEN MATCHED THEN UPDATE SET
            target.account_token         = source.account_token,
            target.persona_id            = source.persona_id,
            target.persona_name          = source.persona_name,
            target.age_band              = source.age_band,
            target.income_band           = source.income_band,
            target.household_income_band = source.household_income_band,
            target.family_status         = source.family_status,
            target.num_dependents        = source.num_dependents,
            target.geography             = source.geography,
            target.state                 = source.state,
            target.zip_prefix            = source.zip_prefix,
            target.account_open_date     = source.account_open_date,
            target.account_type          = source.account_type,
            target.credit_score_band     = source.credit_score_band,
            target.is_active             = source.is_active,
            target.created_at            = source.created_at,
            target.ingested_at           = CURRENT_TIMESTAMP()

        WHEN NOT MATCHED THEN INSERT (
            customer_token, account_token, persona_id, persona_name,
            age_band, income_band, household_income_band,
            family_status, num_dependents, geography, state, zip_prefix,
            account_open_date, account_type, credit_score_band,
            is_active, created_at, ingested_at
        )
        VALUES (
            source.customer_token, source.account_token, source.persona_id,
            source.persona_name, source.age_band, source.income_band,
            source.household_income_band, source.family_status,
            source.num_dependents, source.geography, source.state,
            source.zip_prefix, source.account_open_date, source.account_type,
            source.credit_score_band, source.is_active, source.created_at,
            CURRENT_TIMESTAMP()
        )
    """
    cursor.execute(merge_sql)

    # Snowflake's MERGE returns a single result row whose columns are named
    # "number of rows inserted" and "number of rows updated" (and deleted, for
    # MERGEs with a DELETE clause). The column ORDER isn't guaranteed across
    # versions, so we map by the cursor's column descriptions rather than by
    # positional index. Defensive: if anything is unexpected, counts stay 0
    # and we still report the authoritative before/after total below.
    inserted = 0
    updated = 0
    try:
        row = cursor.fetchone()
        if row and cursor.description:
            col_names = [d[0].lower() for d in cursor.description]
            by_name = dict(zip(col_names, row))
            for name, val in by_name.items():
                if "insert" in name:
                    inserted = int(val)
                elif "update" in name:
                    updated = int(val)
    except Exception as e:
        logger.warning(f"  Could not parse MERGE metrics (non-fatal): {e}")
    logger.info(f"  MERGE: {inserted:,} inserted, {updated:,} updated")

    # Authoritative total — the count is the source of truth regardless of
    # whether the MERGE metrics parsed cleanly.
    cursor.execute("SELECT COUNT(*) FROM RAW.CUSTOMERS")
    total = cursor.fetchone()[0]
    logger.info(f"  Final RAW.CUSTOMERS total: {total:,}")

    return {
        "customers_total": total,
        "customers_inserted": inserted,
        "customers_updated": updated,
        "customers_staged": staged_count,
    }


# =============================================================================
# Transaction load: TRUNCATE + COPY (full reload, idempotent)
# =============================================================================

def load_transactions(cursor, stage_name: str) -> tuple:
    """
    TRUNCATE then COPY INTO transactions with path extraction for
    year_month and day partition columns.

    Returns (total_rows, distinct_days).

    Transactions are immutable events on S3; a full re-COPY is correct and
    idempotent. Spark partitions live in S3 folder names, not parquet content,
    so we use METADATA$FILENAME regex extraction to populate year_month/day.
    """
    logger.info("Truncating RAW.TRANSACTIONS for full reload...")
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

    # Fail-loud guard: NULL partition columns silently break analytics
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
    region = os.environ.get("AWS_REGION_OVERRIDE", os.environ.get("AWS_REGION", "us-east-1"))
    secret_arn = os.environ["SNOWFLAKE_SECRET_ARN"]
    stage_name = os.environ["STAGE_NAME"]

    ingest_date = event.get("ingest_date") or date.today().isoformat()
    logger.info(f"Starting load for ingest_date={ingest_date}")

    creds = fetch_snowflake_credentials(secret_arn, region)
    logger.info(f"Fetched Snowflake credentials for account: {creds['account']}")

    conn = open_snowflake_connection(creds)
    try:
        cursor = conn.cursor()
        try:
            customer_metrics = load_customers(cursor, ingest_date, stage_name)
            transactions_total, transactions_days = load_transactions(cursor, stage_name)
        finally:
            cursor.close()
    finally:
        conn.close()

    result = {
        "status": "success",
        "ingest_date": ingest_date,
        "customers_total": customer_metrics["customers_total"],
        "customers_inserted": customer_metrics["customers_inserted"],
        "customers_updated": customer_metrics["customers_updated"],
        "customers_staged": customer_metrics["customers_staged"],
        "transactions_loaded": transactions_total,
        "transactions_distinct_days": transactions_days,
    }
    logger.info(f"Load complete: {result}")
    return result
