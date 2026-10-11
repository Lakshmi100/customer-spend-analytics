"""
Unit tests for ingestion/pii_tokenizer.py — the local trust-boundary primitives.

All functions under test are pure; no mocking needed. PII_SALT is injected
by tests/conftest.py before this module imports the tokenizer.
"""

import hashlib
import os

import pytest

from ingestion.pii_tokenizer import (
    PII_DROP_COLUMNS,
    PII_TOKENIZE_COLUMNS,
    age_to_band,
    get_pii_columns,
    income_to_band,
    tokenize,
    truncate_zip,
)


# =============================================================================
# tokenize()
# =============================================================================

class TestTokenize:
    def test_deterministic(self):
        assert tokenize("ABC-00012345") == tokenize("ABC-00012345")

    def test_different_inputs_different_tokens(self):
        assert tokenize("ABC-00012345") != tokenize("ABC-00012346")

    def test_token_is_16_char_hex(self):
        token = tokenize("ABC-00012345")
        assert len(token) == 16
        int(token, 16)  # raises ValueError if not hex

    def test_none_returns_none(self):
        assert tokenize(None) is None

    def test_empty_string_returns_none(self):
        assert tokenize("") is None

    def test_salt_is_incorporated(self):
        """Token must NOT equal the unsalted hash — otherwise rainbow-table
        attacks against known customer-ID formats become trivial."""
        value = "ABC-00012345"
        unsalted = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
        assert tokenize(value) != unsalted

    def test_matches_documented_salt_scheme(self):
        """The salt scheme is `{salt}:{value}` — locked in as a contract:
        changing it would silently orphan every token already in Snowflake."""
        value = "ABC-00012345"
        salt = os.environ["PII_SALT"]
        expected = hashlib.sha256(f"{salt}:{value}".encode("utf-8")).hexdigest()[:16]
        assert tokenize(value) == expected


# =============================================================================
# age_to_band() — boundary values
# =============================================================================

class TestAgeBand:
    @pytest.mark.parametrize(
        "age, band",
        [
            (18, "18-24"),
            (24, "18-24"),
            (25, "25-34"),
            (34, "25-34"),
            (35, "35-44"),
            (44, "35-44"),
            (45, "45-54"),
            (54, "45-54"),
            (55, "55-64"),
            (64, "55-64"),
            (65, "65+"),
            (99, "65+"),
        ],
    )
    def test_band_edges(self, age, band):
        assert age_to_band(age) == band

    def test_none_returns_none(self):
        assert age_to_band(None) is None


# =============================================================================
# income_to_band() — boundary values
# =============================================================================

class TestIncomeBand:
    @pytest.mark.parametrize(
        "income, band",
        [
            (0, "no_personal_income"),
            (1, "under_40k"),
            (39_999, "under_40k"),
            (40_000, "40k_75k"),
            (74_999, "40k_75k"),
            (75_000, "75k_125k"),
            (124_999, "75k_125k"),
            (125_000, "125k_200k"),
            (199_999, "125k_200k"),
            (200_000, "over_200k"),
            (1_000_000, "over_200k"),
        ],
    )
    def test_band_edges(self, income, band):
        assert income_to_band(income) == band

    def test_none_returns_none(self):
        assert income_to_band(None) is None


# =============================================================================
# truncate_zip()
# =============================================================================

class TestZipTruncation:
    def test_five_digit_zip(self):
        assert truncate_zip("30309") == "303XX"

    def test_none_returns_none(self):
        assert truncate_zip(None) is None

    def test_non_string_input_coerced(self):
        assert truncate_zip(30309) == "303XX"


# =============================================================================
# get_pii_columns() — the drop/tokenize contract
# =============================================================================

class TestGetPiiColumns:
    def test_flags_drop_and_tokenize_columns(self):
        cols = ["customer_id", "email", "first_name", "amount", "customer_token"]
        flagged = get_pii_columns(cols)
        assert set(flagged) == {"customer_id", "email", "first_name"}

    def test_case_insensitive(self):
        assert get_pii_columns(["EMAIL", "Customer_Id"]) == ["EMAIL", "Customer_Id"]

    def test_safe_columns_never_flagged(self):
        safe = ["customer_token", "account_token", "age_band", "income_band",
                "zip_prefix", "amount", "category", "persona_id"]
        assert get_pii_columns(safe) == []

    def test_drop_and_tokenize_sets_are_disjoint(self):
        """A column must be either dropped or tokenized — never both."""
        assert PII_DROP_COLUMNS & PII_TOKENIZE_COLUMNS == set()
