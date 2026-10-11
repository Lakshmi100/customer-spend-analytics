"""
Unit tests for infra/aws/lambdas/generate_daily_delta/handler.py.

Covers the synthetic delta generators (pure functions) and the S3 parquet
writer (via moto). The upstream timestamp contract is asserted here:
parquet must be written with microsecond timestamps (coerce_timestamps='us')
to match what EMR Spark and the Snowflake named PARQUET_FORMAT expect.
"""

import io
from datetime import date, datetime

import boto3
import pandas as pd
import pyarrow.parquet as pq
import pytest
from moto import mock_aws


# =============================================================================
# generate_new_customer — RAW record, PII present by design (pre-boundary)
# =============================================================================

class TestGenerateNewCustomer:
    def test_contains_pii_fields_pre_boundary(self, generate_daily_delta_handler):
        """The delta generator sits UPSTREAM of the trust boundary: raw PII is
        expected here, and EMR strips it later. If these fields disappear the
        Spark job's drop-list would silently stop being exercised."""
        cust = generate_daily_delta_handler.generate_new_customer(1, "2026-09-18")
        for pii_field in ("customer_id", "account_number", "first_name",
                          "last_name", "email", "phone_number",
                          "date_of_birth", "street_address"):
            assert pii_field in cust, f"missing expected raw field: {pii_field}"

    def test_persona_is_valid(self, generate_daily_delta_handler):
        cust = generate_daily_delta_handler.generate_new_customer(1, "2026-09-18")
        assert cust["persona_id"] in generate_daily_delta_handler.PERSONA_PROFILES
        expected_name = generate_daily_delta_handler.PERSONA_PROFILES[
            cust["persona_id"]]["name"]
        assert cust["persona_name"] == expected_name

    def test_demographics_within_generator_bounds(self, generate_daily_delta_handler):
        cust = generate_daily_delta_handler.generate_new_customer(1, "2026-09-18")
        assert 18 <= cust["age"] <= 85
        assert 25_000 <= cust["annual_income"] <= 350_000
        assert cust["household_income"] >= cust["annual_income"]
        assert cust["account_open_date"] == "2026-09-18"


# =============================================================================
# generate_transaction — persona-tuned synthetic event
# =============================================================================

class TestGenerateTransaction:
    TXN_DATE = date(2026, 9, 18)

    def _txn(self, handler, persona="P04"):
        return handler.generate_transaction(
            seq=7, customer_token="abcd1234efgh5678",
            persona_id=persona, txn_date=self.TXN_DATE,
        )

    def test_timestamp_within_transaction_day(self, generate_daily_delta_handler):
        txn = self._txn(generate_daily_delta_handler)
        ts = txn["transaction_ts"]
        day_start = datetime.combine(self.TXN_DATE, datetime.min.time())
        day_end = datetime.combine(self.TXN_DATE, datetime.max.time())
        assert day_start <= ts <= day_end
        assert txn["transaction_date"] == self.TXN_DATE

    def test_category_matches_persona_preferences(self, generate_daily_delta_handler):
        persona_cats = generate_daily_delta_handler.PERSONA_PROFILES["P04"]["categories"]
        txn = self._txn(generate_daily_delta_handler, persona="P04")
        assert txn["category"] in persona_cats

    def test_amount_within_category_range(self, generate_daily_delta_handler):
        txn = self._txn(generate_daily_delta_handler)
        lo, hi = generate_daily_delta_handler.CATEGORY_AMOUNTS[txn["category"]]
        assert lo <= txn["amount"] <= hi

    def test_unknown_persona_falls_back_to_default(self, generate_daily_delta_handler):
        txn = self._txn(generate_daily_delta_handler, persona="P99-UNKNOWN")
        fallback_cats = generate_daily_delta_handler.PERSONA_PROFILES["P04"]["categories"]
        assert txn["category"] in fallback_cats

    def test_customer_token_passthrough(self, generate_daily_delta_handler):
        """The delta generator reuses existing Snowflake tokens verbatim —
        it must NOT re-tokenize (only the Spark job holds the salt)."""
        txn = self._txn(generate_daily_delta_handler)
        assert txn["customer_token"] == "abcd1234efgh5678"

    def test_transaction_id_format(self, generate_daily_delta_handler):
        txn = self._txn(generate_daily_delta_handler)
        assert txn["transaction_id"] == "TXN-20260918-0000007"


# =============================================================================
# write_parquet_to_s3 — the microsecond-timestamp contract (moto)
# =============================================================================

@mock_aws
class TestWriteParquetToS3:
    BUCKET = "csa-test-raw-bucket"
    REGION = "us-east-1"

    def _make_bucket(self):
        boto3.client("s3", region_name=self.REGION).create_bucket(Bucket=self.BUCKET)

    def test_object_written_and_uri_returned(self, generate_daily_delta_handler):
        self._make_bucket()
        df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
        uri = generate_daily_delta_handler.write_parquet_to_s3(
            df, self.BUCKET, "customers/ingest_date=2026-09-18/delta.parquet"
        )
        assert uri == (
            f"s3://{self.BUCKET}/customers/ingest_date=2026-09-18/delta.parquet"
        )
        body = boto3.client("s3", region_name=self.REGION).get_object(
            Bucket=self.BUCKET,
            Key="customers/ingest_date=2026-09-18/delta.parquet",
        )["Body"].read()
        round_tripped = pd.read_parquet(io.BytesIO(body))
        assert len(round_tripped) == 2

    def test_timestamps_written_as_microseconds(self, generate_daily_delta_handler):
        """Bug #1 upstream contract: pandas defaults to nanosecond timestamps,
        which Snowflake misreads without logical-type handling. The writer must
        coerce to microseconds (timestamp[us]) — same as EMR Spark output."""
        self._make_bucket()
        df = pd.DataFrame({
            "transaction_ts": [datetime(2026, 9, 18, 14, 30, 0)],
            "amount": [42.0],
        })
        generate_daily_delta_handler.write_parquet_to_s3(
            df, self.BUCKET, "transactions/ingest_date=2026-09-18/delta.parquet"
        )
        body = boto3.client("s3", region_name=self.REGION).get_object(
            Bucket=self.BUCKET,
            Key="transactions/ingest_date=2026-09-18/delta.parquet",
        )["Body"].read()

        schema = pq.read_schema(io.BytesIO(body))
        ts_field = schema.field("transaction_ts")
        assert str(ts_field.type) == "timestamp[us]", (
            f"transaction_ts must be timestamp[us], got {ts_field.type} — "
            "nanosecond parquet timestamps corrupt in Snowflake (year ~55M bug)"
        )
