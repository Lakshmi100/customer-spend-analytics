"""
Snowflake setup: creates the database, schemas, and raw tables.

Run this ONCE before running snowflake_loader.py.

Schemas:
    ABC_BANK_ANALYTICS.RAW         — landing zone for ingested parquet
    ABC_BANK_ANALYTICS.STAGING     — dbt will populate this
    ABC_BANK_ANALYTICS.MARTS       — dbt-built marts (customer_360, etc.)

Run:
    python ingestion/snowflake_setup.py
"""

import os
import snowflake.connector
from dotenv import load_dotenv

load_dotenv()


DDL_STATEMENTS = [
    "CREATE DATABASE IF NOT EXISTS ABC_BANK_ANALYTICS",
    "USE DATABASE ABC_BANK_ANALYTICS",
    "CREATE SCHEMA IF NOT EXISTS RAW",
    "CREATE SCHEMA IF NOT EXISTS STAGING",
    "CREATE SCHEMA IF NOT EXISTS MARTS",

    """
    CREATE OR REPLACE FILE FORMAT ABC_BANK_ANALYTICS.RAW.PARQUET_FORMAT
        TYPE = PARQUET
    """,

    """
    CREATE STAGE IF NOT EXISTS ABC_BANK_ANALYTICS.RAW.INGESTION_STAGE
        FILE_FORMAT = ABC_BANK_ANALYTICS.RAW.PARQUET_FORMAT
    """,

    # Customers table — note: NO PII columns. Just tokens and bands.
    """
    CREATE OR REPLACE TABLE ABC_BANK_ANALYTICS.RAW.CUSTOMERS (
        customer_id              STRING       NOT NULL,
        customer_token           STRING       NOT NULL,
        account_token            STRING,
        persona_id               STRING,
        persona_name             STRING,
        age_band                 STRING,
        income_band              STRING,
        household_income_band    STRING,
        family_status            STRING,
        num_dependents           INTEGER,
        geography                STRING,
        state                    STRING,
        zip_prefix               STRING,
        account_open_date        DATE,
        account_type             STRING,
        credit_score_band        STRING,
        is_active                BOOLEAN,
        created_at               TIMESTAMP_NTZ,
        ingested_at              TIMESTAMP_NTZ,
        batch_id                 STRING,
        source_file              STRING
    )
    """,

    """
    CREATE OR REPLACE TABLE ABC_BANK_ANALYTICS.RAW.TRANSACTIONS (
        transaction_id           STRING       NOT NULL,
        customer_id              STRING       NOT NULL,
        customer_token           STRING       NOT NULL,
        transaction_date         DATE         NOT NULL,
        transaction_ts           TIMESTAMP_NTZ,
        amount                   FLOAT        NOT NULL,
        category                 STRING,
        merchant_id              STRING,
        merchant_name            STRING,
        channel                  STRING,
        payment_method           STRING,
        is_recurring             BOOLEAN,
        state                    STRING,
        txn_status               STRING,
        year_month               STRING,
        transaction_year         INTEGER,
        transaction_month        INTEGER,
        ingested_at              TIMESTAMP_NTZ,
        batch_id                 STRING,
        source_file              STRING
    )
    CLUSTER BY (transaction_date, customer_token)
    """,

    "COMMENT ON TABLE ABC_BANK_ANALYTICS.RAW.CUSTOMERS IS 'Tokenized, k-anonymized customer master from ABC Bank ingestion (PII stripped at boundary)'",
    "COMMENT ON TABLE ABC_BANK_ANALYTICS.RAW.TRANSACTIONS IS 'Raw transaction events, partitioned upstream by year_month'",
]


def get_connection():
    return snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
        role=os.getenv("SNOWFLAKE_ROLE"),
    )


def main():
    print("Connecting to Snowflake...")
    conn = get_connection()
    cursor = conn.cursor()

    try:
        for stmt in DDL_STATEMENTS:
            stmt_clean = " ".join(stmt.split())
            preview = stmt_clean[:80] + "..." if len(stmt_clean) > 80 else stmt_clean
            print(f"  → {preview}")
            cursor.execute(stmt)

        print("\n✓ Schema setup complete!")
        print(f"  Database: ABC_BANK_ANALYTICS")
        print(f"  Schemas:  RAW, STAGING, MARTS")
        print(f"  Tables:   RAW.CUSTOMERS (PII-free), RAW.TRANSACTIONS")
        print(f"  Stage:    RAW.INGESTION_STAGE")

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
