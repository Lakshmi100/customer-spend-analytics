"""
Unit tests for ingestion/snowflake_auth.py — shared key-pair auth helper.

No real Snowflake connection is ever opened: snowflake.connector.connect is
patched. Key material is a throwaway RSA key generated per test session
(fixture in conftest.py).
"""

from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import serialization

from ingestion.snowflake_auth import get_connection, load_private_key


class TestLoadPrivateKey:
    def test_missing_env_var_raises_runtime_error(self, monkeypatch):
        monkeypatch.delenv("SNOWFLAKE_PRIVATE_KEY_PATH", raising=False)
        with pytest.raises(RuntimeError, match="SNOWFLAKE_PRIVATE_KEY_PATH"):
            load_private_key()

    def test_missing_key_file_raises_file_not_found(self, monkeypatch, tmp_path):
        monkeypatch.setenv(
            "SNOWFLAKE_PRIVATE_KEY_PATH", str(tmp_path / "does_not_exist.p8")
        )
        with pytest.raises(FileNotFoundError, match="Private key not found"):
            load_private_key()

    def test_valid_pem_returns_parseable_der(self, monkeypatch, test_rsa_key_pem):
        monkeypatch.setenv("SNOWFLAKE_PRIVATE_KEY_PATH", str(test_rsa_key_pem))
        der_bytes = load_private_key()

        assert isinstance(der_bytes, bytes)
        # DER must round-trip through cryptography — proves valid PKCS8 DER
        key = serialization.load_der_private_key(der_bytes, password=None)
        assert key.key_size == 2048


class TestGetConnection:
    def test_env_defaults_passed_to_connector(self, monkeypatch, test_rsa_key_pem):
        monkeypatch.setenv("SNOWFLAKE_PRIVATE_KEY_PATH", str(test_rsa_key_pem))
        monkeypatch.setenv("SNOWFLAKE_ACCOUNT", "TEST-ACCOUNT")
        monkeypatch.setenv("SNOWFLAKE_USER", "TEST_SERVICE_USER")
        monkeypatch.setenv("SNOWFLAKE_WAREHOUSE", "TEST_WH")
        monkeypatch.setenv("SNOWFLAKE_ROLE", "TEST_ROLE")
        monkeypatch.setenv("SNOWFLAKE_DATABASE", "TEST_DB")

        with patch("ingestion.snowflake_auth.snowflake.connector.connect") as mock_connect:
            get_connection()

        kwargs = mock_connect.call_args.kwargs
        assert kwargs["account"] == "TEST-ACCOUNT"
        assert kwargs["user"] == "TEST_SERVICE_USER"
        assert kwargs["warehouse"] == "TEST_WH"
        assert kwargs["role"] == "TEST_ROLE"
        assert isinstance(kwargs["private_key"], bytes)

    def test_kwarg_overrides_win_over_env(self, monkeypatch, test_rsa_key_pem):
        """dbt-style callers override warehouse/role per workload."""
        monkeypatch.setenv("SNOWFLAKE_PRIVATE_KEY_PATH", str(test_rsa_key_pem))
        monkeypatch.setenv("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH")
        monkeypatch.setenv("SNOWFLAKE_ROLE", "ACCOUNTADMIN")

        with patch("ingestion.snowflake_auth.snowflake.connector.connect") as mock_connect:
            get_connection(warehouse="DBT_WH", role="DBT_ROLE")

        kwargs = mock_connect.call_args.kwargs
        assert kwargs["warehouse"] == "DBT_WH"
        assert kwargs["role"] == "DBT_ROLE"
