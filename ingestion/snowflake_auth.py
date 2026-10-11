"""
Shared Snowflake authentication + connection helper.

All local Python code (ingestion, ML) uses this to open Snowflake
connections via RSA key-pair auth. Matches the pattern used by the
AWS Lambda handlers in infra/aws/lambdas/*/handler.py.

Reads:
    SNOWFLAKE_PRIVATE_KEY_PATH   path to PEM-encoded private key
    SNOWFLAKE_ACCOUNT             org-name form: LQZIGNN-AJC44234
    SNOWFLAKE_USER                CSA_SERVICE_USER
    SNOWFLAKE_WAREHOUSE           COMPUTE_WH (or DBT_WH for dbt work)
    SNOWFLAKE_ROLE                ACCOUNTADMIN (or DBT_ROLE for dbt)
    SNOWFLAKE_DATABASE            ABC_BANK_ANALYTICS
    SNOWFLAKE_SCHEMA              RAW (default)

Usage:
    from ingestion.snowflake_auth import get_connection
    conn = get_connection()
    # ... use conn ...
    conn.close()
"""

import os
from pathlib import Path

import snowflake.connector
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization


def load_private_key() -> bytes:
    """
    Load PEM private key from disk, convert to DER bytes for Snowflake
    connector. Path comes from SNOWFLAKE_PRIVATE_KEY_PATH env var.

    Raises FileNotFoundError with a clear message if the key path is wrong.
    """
    key_path = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH")
    if not key_path:
        raise RuntimeError(
            "SNOWFLAKE_PRIVATE_KEY_PATH env var not set. "
            "Expected a PEM-encoded private key file (e.g. /opt/keys/csa_service_key.p8)."
        )

    key_file = Path(key_path)
    if not key_file.exists():
        raise FileNotFoundError(
            f"Private key not found at {key_path}. "
            f"Verify the volume mount in docker-compose.yml."
        )

    with open(key_file, "rb") as f:
        pkey = serialization.load_pem_private_key(
            f.read(),
            password=None,          # no passphrase on our current key
            backend=default_backend(),
        )

    # Snowflake connector wants DER bytes, not PEM
    return pkey.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def get_connection(**overrides):
    """
    Open a Snowflake connection using key-pair authentication.

    Any keyword arguments override the env-var defaults. Useful when
    a specific caller needs a different warehouse or role than the
    process defaults. Example:
        get_connection(warehouse="DBT_WH", role="DBT_ROLE")
    """
    defaults = {
        "account":   os.getenv("SNOWFLAKE_ACCOUNT"),
        "user":      os.getenv("SNOWFLAKE_USER"),
        "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
        "role":      os.getenv("SNOWFLAKE_ROLE"),
        "database":  os.getenv("SNOWFLAKE_DATABASE"),
        "schema":    os.getenv("SNOWFLAKE_SCHEMA", "RAW"),
    }
    defaults.update(overrides)
    defaults["private_key"] = load_private_key()

    return snowflake.connector.connect(**defaults)