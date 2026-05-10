"""
PII tokenization module for ABC Bank ingestion.

The principle: ABC Bank shares customer transaction data with our analytics
platform. We never want raw PII (names, emails, phones) to land in our
analytics database. This module handles the boundary.

Strategy:
- customer_id (internal ABC ID) → customer_token (SHA-256 with salt)
- The token is deterministic so we can join across tables
- The salt makes the token non-reversible without ABC's salt secret
- We keep zip_code at 3-digit precision (k-anonymity)
- We drop names/emails/phones entirely

Note: this synthetic dataset already had no real PII generated, but in
production this module would handle the cleanup before any data
leaves ABC Bank's perimeter.
"""

import hashlib
import os
from typing import Iterable

from dotenv import load_dotenv

load_dotenv()

# The salt should come from env, never hardcoded.
# In production, this would be in a secrets manager (AWS Secrets Manager,
# Snowflake's external function pattern, etc.)
PII_SALT = os.getenv("PII_SALT")
if not PII_SALT or len(PII_SALT) < 32:
    raise ValueError(
        "PII_SALT must be set in .env and at least 32 characters. "
        "Generate one with: python3 -c \"import secrets; print(secrets.token_hex(32))\""
    )


# Columns that must NEVER appear in the analytics layer
PII_DROP_COLUMNS = {
    "first_name", "last_name", "full_name",
    "email", "phone", "phone_number",
    "ssn", "tax_id",
    "street_address", "address_line_1", "address_line_2",
    "date_of_birth",  # we keep age band instead
}

# Columns that get tokenized (replaced with hash) instead of dropped
PII_TOKENIZE_COLUMNS = {
    "customer_id",
    "account_number",
}


def tokenize(value: str) -> str:
    """Produce a deterministic, non-reversible token for an ID."""
    if value is None or value == "":
        return None
    salted = f"{PII_SALT}:{value}"
    return hashlib.sha256(salted.encode("utf-8")).hexdigest()[:16]


def truncate_zip(zip_code: str) -> str:
    """K-anonymity: keep only first 3 digits of zip code."""
    if zip_code is None:
        return None
    return str(zip_code)[:3] + "XX"


def age_to_band(age: int) -> str:
    """Bucket age for k-anonymity."""
    if age is None:
        return None
    if age < 25:
        return "18-24"
    if age < 35:
        return "25-34"
    if age < 45:
        return "35-44"
    if age < 55:
        return "45-54"
    if age < 65:
        return "55-64"
    return "65+"


def income_to_band(income: int) -> str:
    """Bucket income for k-anonymity."""
    if income is None:
        return None
    if income == 0:
        return "no_personal_income"
    if income < 40000:
        return "under_40k"
    if income < 75000:
        return "40k_75k"
    if income < 125000:
        return "75k_125k"
    if income < 200000:
        return "125k_200k"
    return "over_200k"


def get_pii_columns(columns: Iterable[str]) -> list:
    """Return the subset of columns that should be dropped/tokenized."""
    return [c for c in columns if c.lower() in PII_DROP_COLUMNS or c.lower() in PII_TOKENIZE_COLUMNS]


if __name__ == "__main__":
    # Quick self-test
    sample_id = "ABC-00012345"
    token = tokenize(sample_id)
    print(f"Original: {sample_id}")
    print(f"Token:    {token}")
    print(f"Same ID always produces same token: {tokenize(sample_id) == token}")
    print(f"\nAge bands: 22 -> {age_to_band(22)}, 45 -> {age_to_band(45)}, 70 -> {age_to_band(70)}")
    print(f"Income bands: 25000 -> {income_to_band(25000)}, 150000 -> {income_to_band(150000)}")
    print(f"Zip truncation: 30309 -> {truncate_zip('30309')}")
