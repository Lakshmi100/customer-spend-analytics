"""
generate_daily_delta Lambda.

Produces a small synthetic daily delta:
  - Most days: 0 new customers; some days: 3-5 new customers
  - Always: ~50 transactions across a sample of existing customers (+ any new)

Architecture rationale:
  - Writes RAW PII to s3://raw/{date}/ — the EMR Spark job will tokenize
  - Looks up existing customer tokens + personas from Snowflake (RAW.CUSTOMERS)
  - This tests the Lambda → Snowflake path AND keeps persona-based realism

INPUT (event):
    {
        "ingest_date": "2026-05-16"          # optional, defaults to today
        "force_new_customers": <int>          # optional, override randomness
    }

OUTPUT:
    {
        "status": "success",
        "ingest_date": "2026-05-16",
        "new_customers": 3,
        "new_transactions": 52,
        "raw_customers_s3_uri": "s3://.../customers/ingest_date=.../delta.parquet",
        "raw_transactions_s3_uri": "s3://.../transactions/ingest_date=.../delta.parquet"
    }

CONFIGURATION (env vars set by Terraform):
    RAW_BUCKET, SNOWFLAKE_SECRET_ARN, SNOWFLAKE_DATABASE, SNOWFLAKE_SCHEMA,
    SNOWFLAKE_WAREHOUSE, SNOWFLAKE_ROLE
"""

import io
import json
import logging
import os
import random
from datetime import date, datetime, timedelta

import boto3
import pandas as pd
import snowflake.connector
from faker import Faker

# ──────────────────────────────────────────────────────────────────────────
# ADD this import near the top of each handler.py
# ──────────────────────────────────────────────────────────────────────────

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger()
logger.setLevel(logging.INFO)

fake = Faker("en_US")


# =============================================================================
# Constants (kept tiny per design decision — fast Lambda + small EMR cost)
# =============================================================================

# Roll a die per day: 60% no new customers, 40% chance of 3-5 new
NEW_CUSTOMER_PROBABILITY = 0.40
NEW_CUSTOMER_MIN = 3
NEW_CUSTOMER_MAX = 5

# How many existing customers to sample for transaction generation
EXISTING_CUSTOMER_SAMPLE = 200

# Roughly how many transactions to generate per day across all customers
TRANSACTIONS_PER_DAY_MIN = 40
TRANSACTIONS_PER_DAY_MAX = 60

# Persona-driven category weights (light version of personas.py).
# A real production design would query/cache the full personas table;
# this is a sensible subset that keeps the Lambda dependency-light.
PERSONA_PROFILES = {
    "P01": {"name": "Young Single Tech",   "categories": ["dining", "subscription", "transport", "entertainment"]},
    "P02": {"name": "Young Couple Urban",  "categories": ["dining", "groceries", "entertainment", "shopping"]},
    "P03": {"name": "New Parents",         "categories": ["groceries", "baby", "healthcare", "shopping"]},
    "P04": {"name": "Suburban Family",     "categories": ["groceries", "gas", "shopping", "dining"]},
    "P05": {"name": "Affluent Family",     "categories": ["dining", "travel", "shopping", "entertainment"]},
    "P06": {"name": "DINK Professionals",  "categories": ["dining", "travel", "subscription", "entertainment"]},
    "P07": {"name": "Single Parent",       "categories": ["groceries", "healthcare", "shopping", "gas"]},
    "P08": {"name": "Frugal Family",       "categories": ["groceries", "gas", "utilities", "shopping"]},
    "P09": {"name": "Pre-Retirement",      "categories": ["dining", "travel", "healthcare", "groceries"]},
    "P10": {"name": "Active Retirees",     "categories": ["travel", "dining", "healthcare", "entertainment"]},
    "P11": {"name": "Empty Nesters",       "categories": ["dining", "travel", "shopping", "groceries"]},
    "P12": {"name": "Fixed-Income Senior", "categories": ["groceries", "healthcare", "utilities", "pharmacy"]},
    "P13": {"name": "College Student",     "categories": ["dining", "entertainment", "subscription", "transport"]},
    "P14": {"name": "Grad Student",        "categories": ["dining", "subscription", "groceries", "transport"]},
    "P15": {"name": "Gig Worker",          "categories": ["gas", "dining", "transport", "subscription"]},
    "P16": {"name": "Small Biz Owner",     "categories": ["business", "dining", "gas", "travel"]},
    "P17": {"name": "Tech Professional",   "categories": ["dining", "subscription", "travel", "entertainment"]},
    "P18": {"name": "Healthcare Worker",   "categories": ["gas", "dining", "groceries", "healthcare"]},
    "P19": {"name": "Teacher",             "categories": ["groceries", "dining", "subscription", "shopping"]},
    "P20": {"name": "Blue Collar",         "categories": ["gas", "groceries", "dining", "utilities"]},
}

CATEGORY_AMOUNTS = {
    "dining":        (10, 80),
    "groceries":     (20, 150),
    "gas":           (20, 60),
    "shopping":      (15, 200),
    "subscription":  (5, 25),
    "transport":     (5, 30),
    "entertainment": (10, 80),
    "travel":        (100, 800),
    "healthcare":    (20, 250),
    "utilities":     (50, 200),
    "baby":          (15, 100),
    "business":      (30, 500),
    "pharmacy":      (5, 50),
}

CHANNELS = ["online", "in_store"]
PAYMENT_METHODS = ["debit", "credit"]
TXN_STATUSES = ["posted", "posted", "posted", "pending"]  # weighted toward posted


# =============================================================================
# Secrets Manager
# =============================================================================

def fetch_snowflake_credentials(secret_arn: str, region: str) -> dict:
    """
    Read Snowflake credentials from Secrets Manager.

    New schema (key-pair auth — replaces password auth that failed under
    Snowflake's MFA-required policy on paid accounts):
        {
            "account":     "<account locator>",
            "user":        "CSA_SERVICE_USER",
            "private_key": "<PEM-encoded PKCS8 private key>"
        }
    """
    client = boto3.client("secretsmanager", region_name=region)
    response = client.get_secret_value(SecretId=secret_arn)
    creds = json.loads(response["SecretString"])

    required = {"account", "user", "private_key"}
    missing = required - set(creds.keys())
    if missing:
        raise ValueError(
            f"Snowflake secret missing required keys: {sorted(missing)}. "
            f"Expected schema: account, user, private_key. "
            f"Got keys: {sorted(creds.keys())}"
        )
    return creds

def open_snowflake_connection(creds: dict):
    """
    Open a Snowflake connection using key-pair authentication.

    snowflake-connector-python expects the private key as DER bytes,
    so we load the PEM string and re-serialize to DER.
    """
    # Load PEM-encoded private key (no passphrase — for production with
    # passphrase, add password=... here and store passphrase separately
    # in Secrets Manager).
    private_key_pem = creds["private_key"].encode("utf-8")
    pkey = serialization.load_pem_private_key(
        private_key_pem,
        password=None,
        backend=default_backend(),
    )

    # Snowflake connector wants the key as DER bytes
    pkey_bytes = pkey.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    return snowflake.connector.connect(
        account=creds["account"],
        user=creds["user"],
        private_key=pkey_bytes,
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=os.environ["SNOWFLAKE_SCHEMA"],
        role=os.environ["SNOWFLAKE_ROLE"],
        network_timeout=60,
        login_timeout=30,
    )

# =============================================================================
# Snowflake — read existing customer tokens + personas
# =============================================================================

# =============================================================================
# Replace this call to use open_snowflake_connection() instead of
# duplicating the connect parameters — both safer (one place to maintain
# auth) and necessary (the old version still references creds["password"]
# which no longer exists after the key-pair migration).
# =============================================================================


def fetch_existing_customers(creds: dict, sample_size: int) -> list:
    """
    Returns a list of dicts: [{"customer_token": "...", "persona_id": "P11"}, ...]

    Uses TABLESAMPLE for efficient random sampling at scale.

    Refactored to use the shared open_snowflake_connection helper rather
    than duplicating connection parameters — single source of truth for
    auth logic.
    """
    conn = open_snowflake_connection(creds)
    try:
        cursor = conn.cursor()
        try:
            cursor.execute(f"""
                SELECT customer_token, persona_id
                FROM RAW.CUSTOMERS
                SAMPLE ({sample_size} ROWS)
            """)
            rows = cursor.fetchall()
            return [{"customer_token": t, "persona_id": p} for t, p in rows]
        finally:
            cursor.close()
    finally:
        conn.close()


# =============================================================================
# Generators
# =============================================================================

def generate_new_customer(seq: int, ingest_date: str) -> dict:
    """Generate one new RAW customer record (with PII — Spark will tokenize)."""
    persona_id = random.choice(list(PERSONA_PROFILES.keys()))
    persona_name = PERSONA_PROFILES[persona_id]["name"]
    age = random.randint(18, 85)
    annual_income = random.randint(25000, 350000)
    household_income = annual_income + random.randint(0, 200000)
    state = fake.state_abbr()

    first = fake.first_name()
    last = fake.last_name()

    return {
        "customer_id": f"ABC-{int(datetime.now().timestamp()):08d}{seq:02d}",
        "account_number": str(random.randint(1000000000, 9999999999)),
        "first_name": first,
        "last_name": last,
        "full_name": f"{first} {last}",
        "email": fake.email(),
        "phone_number": fake.phone_number(),
        "date_of_birth": (datetime.now().date() - timedelta(days=age * 365)).isoformat(),
        "street_address": fake.street_address(),
        "persona_id": persona_id,
        "persona_name": persona_name,
        "age": age,
        "annual_income": annual_income,
        "household_income": household_income,
        "family_status": random.choice(["single", "married_no_kids", "married_with_kids", "divorced", "widowed"]),
        "num_dependents": random.randint(0, 4),
        "geography": random.choice(["urban", "suburban", "rural"]),
        "state": state,
        "zip_code": fake.zipcode(),
        "account_open_date": ingest_date,
        "account_type": random.choice(["basic", "premium", "private"]),
        "credit_score_band": random.choice(["fair", "good", "very_good", "excellent"]),
        "is_active": True,
        "created_at": datetime.now(),
    }


def generate_transaction(seq: int, customer_token: str, persona_id: str, txn_date: date) -> dict:
    """Generate one transaction tuned to the customer's persona category preferences."""
    persona = PERSONA_PROFILES.get(persona_id, PERSONA_PROFILES["P04"])  # default fallback
    category = random.choice(persona["categories"])
    amount_lo, amount_hi = CATEGORY_AMOUNTS[category]
    amount = round(random.uniform(amount_lo, amount_hi), 2)

    return {
        "transaction_id": f"TXN-{txn_date.strftime('%Y%m%d')}-{seq:07d}",
        "customer_token": customer_token,
        "transaction_date": txn_date,
        "transaction_ts": datetime.combine(txn_date, datetime.min.time())
                          + timedelta(seconds=random.randint(0, 86399)),
        "amount": amount,
        "category": category,
        "merchant_id": f"M-{random.randint(10000, 99999)}",
        "merchant_name": fake.company(),
        "channel": random.choice(CHANNELS),
        "payment_method": random.choice(PAYMENT_METHODS),
        "is_recurring": random.random() < 0.15,
        "state": fake.state_abbr(),
        "txn_status": random.choice(TXN_STATUSES),
    }


# =============================================================================
# S3 writers
# =============================================================================

def write_parquet_to_s3(df: pd.DataFrame, bucket: str, key: str) -> str:
    """Write a DataFrame as parquet to S3. Microsecond timestamps to match Spark."""
    s3 = boto3.client("s3")
    buf = io.BytesIO()
    df.to_parquet(buf, index=False, coerce_timestamps="us")  # match EMR Spark expectations
    buf.seek(0)
    s3.put_object(Bucket=bucket, Key=key, Body=buf.getvalue())
    return f"s3://{bucket}/{key}"


# =============================================================================
# Lambda entry point
# =============================================================================

def lambda_handler(event, context):
    region = os.environ.get("AWS_REGION_OVERRIDE", os.environ.get("AWS_REGION", "us-east-1"))
    raw_bucket = os.environ["RAW_BUCKET"]
    secret_arn = os.environ["SNOWFLAKE_SECRET_ARN"]

    ingest_date_str = event.get("ingest_date") or date.today().isoformat()
    ingest_date = datetime.strptime(ingest_date_str, "%Y-%m-%d").date()
    logger.info(f"Generating daily delta for ingest_date={ingest_date_str}")

    # ----- 1. Decide how many new customers (event override OR random roll) -----
    if "force_new_customers" in event:
        n_new = int(event["force_new_customers"])
        logger.info(f"Forced new_customers={n_new} (via event)")
    elif random.random() < NEW_CUSTOMER_PROBABILITY:
        n_new = random.randint(NEW_CUSTOMER_MIN, NEW_CUSTOMER_MAX)
        logger.info(f"Rolled {n_new} new customers today (random)")
    else:
        n_new = 0
        logger.info("Rolled 0 new customers today (random)")

    # ----- 2. Look up existing customers from Snowflake -----
    creds = fetch_snowflake_credentials(secret_arn, region)
    existing = fetch_existing_customers(creds, EXISTING_CUSTOMER_SAMPLE)
    logger.info(f"Sampled {len(existing)} existing customers from Snowflake")

    # ----- 3. Generate any new customer records -----
    customer_outputs = []
    new_customer_token_proxies = []  # tokens-to-be (placeholder; Spark will real-tokenize)
    if n_new > 0:
        new_customers = [generate_new_customer(i, ingest_date_str) for i in range(n_new)]
        customer_df = pd.DataFrame(new_customers)
        customers_key = f"customers/ingest_date={ingest_date_str}/delta.parquet"
        customer_outputs.append(write_parquet_to_s3(customer_df, raw_bucket, customers_key))
        logger.info(f"Wrote {n_new} new customers to S3")

        # New customers are usable in transactions too (use raw customer_id as a proxy
        # token; the Spark job will re-tokenize. For the synthetic delta, this is fine.)
        new_customer_token_proxies = [
            {"customer_token": c["customer_id"], "persona_id": c["persona_id"]}
            for c in new_customers
        ]

    # ----- 4. Generate transactions: mix existing + (any) new customers -----
    transaction_pool = existing + new_customer_token_proxies
    n_txn = random.randint(TRANSACTIONS_PER_DAY_MIN, TRANSACTIONS_PER_DAY_MAX)

    transactions = []
    for i in range(n_txn):
        customer = random.choice(transaction_pool)
        transactions.append(
            generate_transaction(
                seq=i,
                customer_token=customer["customer_token"],
                persona_id=customer["persona_id"],
                txn_date=ingest_date,
            )
        )

    transactions_df = pd.DataFrame(transactions)
    transactions_key = f"transactions/ingest_date={ingest_date_str}/delta.parquet"
    transactions_uri = write_parquet_to_s3(transactions_df, raw_bucket, transactions_key)
    logger.info(f"Wrote {n_txn} transactions to S3")

    result = {
        "status": "success",
        "ingest_date": ingest_date_str,
        "new_customers": n_new,
        "new_transactions": n_txn,
        "raw_customers_s3_uri": customer_outputs[0] if customer_outputs else None,
        "raw_transactions_s3_uri": transactions_uri,
    }
    logger.info(f"Delta complete: {result}")
    return result
