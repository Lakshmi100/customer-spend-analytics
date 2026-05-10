"""
Generate 1,000 synthetic ABC Bank customers WITH realistic PII.

This is what ABC Bank would have in their customer master. The PII is
deliberately included so our pii_tokenizer module has something real to
strip during ingestion — demonstrating the trust boundary between the
bank's internal data and our analytics platform.

PII fields included (and stripped during ingestion):
    - first_name, last_name, full_name
    - email
    - phone_number
    - date_of_birth (replaced with age_band downstream)
    - street_address (replaced with zip_prefix downstream)
    - account_number (tokenized)

Output: data/raw/customers.parquet (and CSV for inspection)
"""

import hashlib
import random
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

from personas import PERSONAS, get_persona

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
fake = Faker("en_US")
Faker.seed(SEED)

NUM_CUSTOMERS = 1000
OUTPUT_DIR = Path("data/raw")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


PERSONA_DISTRIBUTION = {
    "P01": 35, "P02": 65, "P03": 30, "P04": 50, "P05": 60,
    "P06": 90, "P07": 40, "P08": 50, "P09": 60, "P10": 40,
    "P11": 70, "P12": 65, "P13": 55, "P14": 70, "P15": 50,
    "P16": 60, "P17": 30, "P18": 30, "P19": 30, "P20": 20,
}

assert sum(PERSONA_DISTRIBUTION.values()) == NUM_CUSTOMERS


def hash_token(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def credit_score_for_persona(persona_id: str) -> str:
    high = {"P03", "P07", "P11", "P12", "P15", "P20"}
    good = {"P02", "P04", "P06", "P10", "P13", "P14", "P17", "P19"}
    fair = {"P05", "P08", "P09", "P16", "P18"}
    low = {"P01"}
    if persona_id in high:
        return random.choices(["very_good", "excellent"], weights=[0.3, 0.7])[0]
    if persona_id in good:
        return random.choices(["good", "very_good", "excellent"], weights=[0.3, 0.5, 0.2])[0]
    if persona_id in fair:
        return random.choices(["fair", "good", "very_good"], weights=[0.3, 0.5, 0.2])[0]
    if persona_id in low:
        return random.choices(["poor", "fair", "good"], weights=[0.3, 0.5, 0.2])[0]
    return "good"


def account_type_for_persona(persona_id: str) -> str:
    premium = {"P03", "P07", "P11", "P12", "P15", "P20"}
    if persona_id in premium:
        return random.choices(["checking", "premium"], weights=[0.3, 0.7])[0]
    return random.choices(["checking", "savings"], weights=[0.7, 0.3])[0]


def gender_for_persona_name(persona_name: str) -> str:
    """Bias gender from persona for naming realism."""
    female_hints = ["Sasha", "Maya", "Linda", "Jenna", "Aisha", "Susan", "Eleanor",
                    "Maria", "Carol", "Pat", "Vanessa"]
    male_hints = ["Alex", "Tyler", "Raj", "Sam", "Marcus", "Bob", "Dev", "James",
                  "Ron", "Jordan", "Kai"]
    for f in female_hints:
        if f in persona_name:
            return "F"
    for m in male_hints:
        if m in persona_name:
            return "M"
    return random.choice(["F", "M"])


def date_of_birth_from_age(age: int) -> date:
    today = date.today()
    year = today.year - age
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return date(year, month, day)


def generate_customer(seq: int, persona_id: str) -> dict:
    persona = get_persona(persona_id)

    age = random.randint(*persona.age_range)
    income = random.randint(*persona.income_range)

    if persona.family_status in ("married_no_kids", "married_with_kids"):
        spouse_income = int(income * random.uniform(0.6, 1.3))
        household_income = income + spouse_income
    else:
        household_income = income

    num_dependents = random.randint(*persona.num_dependents)

    # === REAL PII generation ===
    gender = gender_for_persona_name(persona.name)
    first_name = fake.first_name_female() if gender == "F" else fake.first_name_male()
    last_name = fake.last_name()
    full_name = f"{first_name} {last_name}"

    email_provider = random.choices(
        ["gmail.com", "yahoo.com", "outlook.com", "icloud.com", "hotmail.com"],
        weights=[0.55, 0.15, 0.12, 0.10, 0.08],
    )[0]
    email = f"{first_name.lower()}.{last_name.lower()}{random.randint(1, 999)}@{email_provider}"

    phone_number = fake.phone_number()
    street_address = fake.street_address()
    date_of_birth = date_of_birth_from_age(age)

    customer_id = f"ABC-{seq:08d}"
    account_number = f"{random.randint(1000000000, 9999999999)}"
    customer_token = hash_token(customer_id + str(SEED))

    state = fake.state_abbr()
    zip_code = fake.zipcode()

    days_open = random.randint(30, 10 * 365)
    account_open_date = date.today() - timedelta(days=days_open)

    return {
        # Internal IDs
        "customer_id": customer_id,
        "account_number": account_number,
        "customer_token": customer_token,
        # PII (stripped during ingestion)
        "first_name": first_name,
        "last_name": last_name,
        "full_name": full_name,
        "email": email,
        "phone_number": phone_number,
        "date_of_birth": date_of_birth,
        "street_address": street_address,
        # Demographics
        "persona_id": persona.persona_id,
        "persona_name": persona.name,
        "age": age,
        "annual_income": income,
        "household_income": household_income,
        "family_status": persona.family_status,
        "num_dependents": num_dependents,
        "geography": persona.geography,
        "state": state,
        "zip_code": zip_code,
        # Account attributes
        "account_open_date": account_open_date,
        "account_type": account_type_for_persona(persona.persona_id),
        "credit_score_band": credit_score_for_persona(persona.persona_id),
        "is_active": random.choices([True, False], weights=[0.95, 0.05])[0],
        "created_at": datetime.now(),
    }


def main():
    print(f"Generating {NUM_CUSTOMERS} customers WITH realistic PII...")
    print("(This is what ABC Bank's internal customer master would look like.)\n")

    rows = []
    seq = 1
    for persona_id, count in PERSONA_DISTRIBUTION.items():
        for _ in range(count):
            rows.append(generate_customer(seq, persona_id))
            seq += 1

    df = pd.DataFrame(rows)
    df = df.sample(frac=1, random_state=SEED).reset_index(drop=True)

    parquet_path = OUTPUT_DIR / "customers.parquet"
    csv_path = OUTPUT_DIR / "customers.csv"
    df.to_parquet(parquet_path, index=False)
    df.to_csv(csv_path, index=False)

    print(f"✓ Wrote {len(df)} customers to:")
    print(f"  - {parquet_path}")
    print(f"  - {csv_path}")

    print(f"\n=== PII columns present (will be stripped during ingestion) ===")
    pii_cols = ["first_name", "last_name", "email", "phone_number",
                "date_of_birth", "street_address", "account_number"]
    print(df[pii_cols].head(3).to_string())

    print(f"\n=== Persona breakdown ===")
    print(df["persona_name"].value_counts().to_string())

    print(f"\n=== Income stats ===")
    print(df["annual_income"].describe().round(0).to_string())

    print(f"\n=== Family status ===")
    print(df["family_status"].value_counts().to_string())


if __name__ == "__main__":
    main()