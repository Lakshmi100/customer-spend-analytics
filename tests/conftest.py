"""
Shared pytest fixtures for the customer-spend-analytics unit test suite.

IMPORTANT ordering: PII_SALT must be set in the environment BEFORE any test
imports ingestion.pii_tokenizer — that module validates the salt at import
time (>= 32 chars) and raises otherwise. os.environ.setdefault runs at
conftest import, which pytest guarantees happens before test collection.
(load_dotenv in the source modules does NOT override already-set env vars,
so the test salt below always wins over .env.)
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Make `ingestion`, `ml`, `api`, `data_generation` importable from tests
sys.path.insert(0, str(PROJECT_ROOT))

# Deterministic test salt (>= 32 chars) — set BEFORE pii_tokenizer import
os.environ.setdefault(
    "PII_SALT", "unit-test-salt-0123456789abcdef0123456789abcdef"
)


# =============================================================================
# Fake Snowflake cursor — records executed SQL for assertion-style tests
# =============================================================================

class FakeCursor:
    """
    Minimal stand-in for snowflake.connector cursor.

    - Records every SQL string passed to execute() in .executed
    - fetchone()/fetchall() pop pre-loaded results from .results (FIFO);
      returns a safe default when exhausted
    - .description mimics the cursor metadata for MERGE-metrics parsing
    """

    def __init__(self, results=None, description=None):
        self.executed = []
        self.results = list(results or [])
        self.description = description
        self.closed = False

    def execute(self, sql, *args, **kwargs):
        self.executed.append(sql)
        return self

    def _next(self, default):
        if self.results:
            return self.results.pop(0)
        return default

    def fetchone(self):
        return self._next((0,))

    def fetchall(self):
        return self._next([])

    def close(self):
        self.closed = True

    # --- assertion helpers -------------------------------------------------
    def sql_containing(self, fragment: str) -> list:
        """All executed statements containing the fragment (case-insensitive)."""
        return [s for s in self.executed if fragment.lower() in s.lower()]


@pytest.fixture
def fake_cursor():
    return FakeCursor()


# =============================================================================
# Throwaway RSA key for snowflake_auth PEM→DER tests
# =============================================================================

@pytest.fixture(scope="session")
def test_rsa_key_pem(tmp_path_factory) -> Path:
    """Generate a fresh 2048-bit RSA private key (PEM/PKCS8, no passphrase).

    Session-scoped: key generation costs ~0.1s, no need to repeat per test.
    NEVER a real credential — generated in a temp dir, discarded after run.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_path = tmp_path_factory.mktemp("keys") / "test_service_key.p8"
    key_path.write_bytes(pem)
    return key_path


# =============================================================================
# Lambda handler loader — the handler dirs are not python packages
# =============================================================================

LAMBDA_ENV_DEFAULTS = {
    "SNOWFLAKE_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:000000000000:secret:test",
    "SNOWFLAKE_DATABASE": "ABC_BANK_ANALYTICS",
    "SNOWFLAKE_SCHEMA": "RAW",
    "SNOWFLAKE_WAREHOUSE": "COMPUTE_WH",
    "SNOWFLAKE_ROLE": "ACCOUNTADMIN",
    "STAGE_NAME": "csa_processed_stage",
    "RAW_BUCKET": "csa-test-raw-bucket",
    "AWS_DEFAULT_REGION": "us-east-1",
    # moto needs fake creds present
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
}


def load_lambda_handler(lambda_name: str):
    """Import infra/aws/lambdas/<lambda_name>/handler.py as a module.

    Sets required env vars first (handlers read os.environ at call time).
    Each lambda gets a unique module name so both handlers can be loaded
    in one pytest session without clashing.
    """
    for k, v in LAMBDA_ENV_DEFAULTS.items():
        os.environ.setdefault(k, v)

    handler_path = (
        PROJECT_ROOT / "infra" / "aws" / "lambdas" / lambda_name / "handler.py"
    )
    module_name = f"lambda_{lambda_name}_handler"
    spec = importlib.util.spec_from_file_location(module_name, handler_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def snowflake_loader_handler():
    return load_lambda_handler("snowflake_loader")


@pytest.fixture(scope="session")
def generate_daily_delta_handler():
    return load_lambda_handler("generate_daily_delta")
