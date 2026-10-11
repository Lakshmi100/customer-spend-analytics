"""
Snowflake IO helper for the ML layer.

A small wrapper around snowflake-connector-python that:
- Loads credentials from .env
- Returns pandas DataFrames from queries
- Uses the dbt warehouse so ML reads the freshly-built marts

Usage:
    from ml.snowflake_io import query_snowflake
    df = query_snowflake("SELECT * FROM MARTS.CUSTOMER_360")
"""

import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    """Open Snowflake connection via shared key-pair auth helper."""
    from ingestion.snowflake_auth import get_connection as _kp_connect
    return _kp_connect()

def query_snowflake(sql: str) -> pd.DataFrame:
    """Run a SQL query, return as pandas DataFrame."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        df = cursor.fetch_pandas_all()
        cursor.close()
        # Snowflake returns uppercase column names; normalize to lowercase for Python convention
        df.columns = [c.lower() for c in df.columns]
        return df
    finally:
        conn.close()


if __name__ == "__main__":
    # Quick smoke test
    df = query_snowflake("SELECT COUNT(*) AS n FROM CUSTOMER_360")
    print(f"✓ Connected. CUSTOMER_360 has {df['n'].iloc[0]:,} rows")
