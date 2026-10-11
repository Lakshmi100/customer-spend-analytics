"""
Unit tests for infra/aws/lambdas/snowflake_loader/handler.py.

This is the REGRESSION SUITE for the two 2026-09-09 production bugs:

  Bug #1 (timestamp corruption): the customers COPY used an inline
    FILE_FORMAT = (TYPE = PARQUET), which does NOT carry USE_LOGICAL_TYPE=TRUE.
    Fix: named format ABC_BANK_ANALYTICS.RAW.PARQUET_FORMAT. Tests here assert
    the named format is used and the inline form never reappears.

  _SUCCESS crash: the transactions COPY read Spark's _SUCCESS marker file
    ("Parquet magic bytes not found") and — because TRUNCATE had already
    run — left RAW.TRANSACTIONS empty. Fix: PATTERN = '.*[.]parquet'.

No Snowflake connection is opened: SQL is captured via FakeCursor.
Secrets Manager is faked in-process via moto.
"""

import json

import boto3
import pytest
from moto import mock_aws

from tests.conftest import FakeCursor


# =============================================================================
# load_customers — MERGE pattern
# =============================================================================

class TestLoadCustomers:
    def _run(self, handler, cursor=None):
        cursor = cursor or FakeCursor(
            results=[
                (5,),        # SELECT COUNT(*) FROM RAW.CUSTOMERS_STAGE
                (2, 3),      # MERGE result row (parsed by description below)
                (1005,),     # SELECT COUNT(*) FROM RAW.CUSTOMERS
            ],
        )
        metrics = handler.load_customers(cursor, "2026-09-18", "csa_processed_stage")
        return cursor, metrics

    def test_copy_uses_named_parquet_format(self, snowflake_loader_handler):
        """Bug #1 regression: named format carries USE_LOGICAL_TYPE=TRUE."""
        cursor, _ = self._run(snowflake_loader_handler)
        copy_sqls = cursor.sql_containing("COPY INTO RAW.CUSTOMERS_STAGE")
        assert len(copy_sqls) == 1
        assert "FORMAT_NAME = 'ABC_BANK_ANALYTICS.RAW.PARQUET_FORMAT'" in copy_sqls[0]

    def test_copy_never_uses_inline_parquet_type(self, snowflake_loader_handler):
        """The inline form silently loses USE_LOGICAL_TYPE — must never return."""
        cursor, _ = self._run(snowflake_loader_handler)
        copy_sqls = cursor.sql_containing("COPY INTO RAW.CUSTOMERS_STAGE")
        assert "TYPE = PARQUET" not in copy_sqls[0]

    def test_copy_scoped_to_ingest_date_partition(self, snowflake_loader_handler):
        cursor, _ = self._run(snowflake_loader_handler)
        copy_sql = cursor.sql_containing("COPY INTO RAW.CUSTOMERS_STAGE")[0]
        assert "customers/ingest_date=2026-09-18/" in copy_sql

    def test_copy_has_parquet_pattern(self, snowflake_loader_handler):
        cursor, _ = self._run(snowflake_loader_handler)
        copy_sql = cursor.sql_containing("COPY INTO RAW.CUSTOMERS_STAGE")[0]
        assert "PATTERN = '.*[.]parquet'" in copy_sql

    def test_merge_joins_on_customer_token(self, snowflake_loader_handler):
        cursor, _ = self._run(snowflake_loader_handler)
        merge_sqls = cursor.sql_containing("MERGE INTO RAW.CUSTOMERS")
        assert len(merge_sqls) == 1
        assert "target.customer_token = source.customer_token" in merge_sqls[0]

    def test_merge_never_updates_the_join_key(self, snowflake_loader_handler):
        """Updating customer_token in WHEN MATCHED would be destructive."""
        cursor, _ = self._run(snowflake_loader_handler)
        merge_sql = cursor.sql_containing("MERGE INTO RAW.CUSTOMERS")[0]
        matched_clause = merge_sql.split("WHEN NOT MATCHED")[0]
        update_part = matched_clause.split("WHEN MATCHED")[1]
        assert "target.customer_token " not in update_part
        assert "target.customer_token=" not in update_part

    def test_staging_table_recreated_before_copy(self, snowflake_loader_handler):
        """CREATE OR REPLACE TEMP table must precede the COPY (stale-state guard)."""
        cursor, _ = self._run(snowflake_loader_handler)
        create_idx = next(
            i for i, s in enumerate(cursor.executed)
            if "CREATE OR REPLACE TEMPORARY TABLE RAW.CUSTOMERS_STAGE" in s
        )
        copy_idx = next(
            i for i, s in enumerate(cursor.executed)
            if "COPY INTO RAW.CUSTOMERS_STAGE" in s
        )
        assert create_idx < copy_idx

    def test_merge_metrics_parsed_by_column_name(self, snowflake_loader_handler):
        """Column ORDER of the MERGE result row isn't guaranteed — parse by name.
        Here we deliberately reverse the order (updated first) to prove it."""
        cursor = FakeCursor(
            results=[(5,), (3, 2), (1005,)],
        )
        # description is set for the whole run; the MERGE fetch reads it
        cursor.description = [
            ("number of rows updated",), ("number of rows inserted",),
        ]
        _, metrics = self._run(snowflake_loader_handler, cursor)
        assert metrics["customers_inserted"] == 2
        assert metrics["customers_updated"] == 3

    def test_returns_authoritative_total(self, snowflake_loader_handler):
        _, metrics = self._run(snowflake_loader_handler)
        assert metrics["customers_total"] == 1005
        assert metrics["customers_staged"] == 5


# =============================================================================
# load_transactions — TRUNCATE + COPY pattern
# =============================================================================

class TestLoadTransactions:
    def _run(self, handler, count_row=(1000, 700, 0)):
        cursor = FakeCursor(results=[count_row])
        total, days = handler.load_transactions(
            cursor, "csa_processed_stage", "2026-09-18"
        )
        return cursor, total, days

    def test_copy_has_parquet_pattern(self, snowflake_loader_handler):
        """_SUCCESS-crash regression: Spark marker files must be filtered out."""
        cursor, _, _ = self._run(snowflake_loader_handler)
        copy_sql = cursor.sql_containing("COPY INTO RAW.TRANSACTIONS")[0]
        assert "PATTERN = '.*[.]parquet'" in copy_sql

    def test_copy_uses_named_parquet_format(self, snowflake_loader_handler):
        cursor, _, _ = self._run(snowflake_loader_handler)
        copy_sql = cursor.sql_containing("COPY INTO RAW.TRANSACTIONS")[0]
        assert "FORMAT_NAME = 'ABC_BANK_ANALYTICS.RAW.PARQUET_FORMAT'" in copy_sql

    def test_truncate_runs_strictly_before_copy(self, snowflake_loader_handler):
        cursor, _, _ = self._run(snowflake_loader_handler)
        truncate_idx = next(
            i for i, s in enumerate(cursor.executed)
            if "TRUNCATE TABLE RAW.TRANSACTIONS" in s
        )
        copy_idx = next(
            i for i, s in enumerate(cursor.executed)
            if "COPY INTO RAW.TRANSACTIONS" in s
        )
        assert truncate_idx < copy_idx

    def test_lineage_columns_populated(self, snowflake_loader_handler):
        """ingested_at / batch_id / source_file made Bug #2 attributable —
        they must stay in the COPY projection."""
        cursor, _, _ = self._run(snowflake_loader_handler)
        copy_sql = cursor.sql_containing("COPY INTO RAW.TRANSACTIONS")[0]
        assert "CURRENT_TIMESTAMP()::TIMESTAMP_NTZ AS ingested_at" in copy_sql
        assert "aws_batch_2026-09-18_" in copy_sql          # batch_id literal
        assert "METADATA$FILENAME AS source_file" in copy_sql

    def test_partition_columns_extracted_from_path(self, snowflake_loader_handler):
        cursor, _, _ = self._run(snowflake_loader_handler)
        copy_sql = cursor.sql_containing("COPY INTO RAW.TRANSACTIONS")[0]
        assert "year_month=([^/]+)" in copy_sql
        assert "day=([^/]+)" in copy_sql

    def test_returns_counts(self, snowflake_loader_handler):
        _, total, days = self._run(
            snowflake_loader_handler, count_row=(1_621_824, 768, 0)
        )
        assert total == 1_621_824
        assert days == 768

    def test_null_day_guard_fails_loud(self, snowflake_loader_handler):
        """NULL partition columns silently break analytics — must abort."""
        with pytest.raises(ValueError, match="DATA QUALITY FAILURE"):
            self._run(snowflake_loader_handler, count_row=(100, 5, 3))


# =============================================================================
# fetch_snowflake_credentials — Secrets Manager (moto)
# =============================================================================

@mock_aws
class TestFetchCredentials:
    REGION = "us-east-1"

    def _create_secret(self, payload: dict) -> str:
        client = boto3.client("secretsmanager", region_name=self.REGION)
        resp = client.create_secret(
            Name="csa-test-snowflake", SecretString=json.dumps(payload)
        )
        return resp["ARN"]

    def test_valid_secret_returned(self, snowflake_loader_handler):
        arn = self._create_secret(
            {"account": "TEST-ACCT", "user": "CSA_SERVICE_USER",
             "private_key": "-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----"}
        )
        creds = snowflake_loader_handler.fetch_snowflake_credentials(arn, self.REGION)
        assert creds["account"] == "TEST-ACCT"
        assert creds["user"] == "CSA_SERVICE_USER"

    def test_missing_keys_raise_with_clear_message(self, snowflake_loader_handler):
        """Key-pair migration guard: old password-schema secrets must fail loud."""
        arn = self._create_secret({"account": "TEST-ACCT", "password": "old-schema"})
        with pytest.raises(ValueError, match="missing required keys"):
            snowflake_loader_handler.fetch_snowflake_credentials(arn, self.REGION)
