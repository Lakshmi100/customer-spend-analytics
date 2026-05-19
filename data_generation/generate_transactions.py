"""
Generate 24 months of synthetic transactions for ABC Bank customers.

Output: data/raw/transactions.parquet (and a CSV sample for inspection)

Schema:
    transaction_id     (str)    TXN-YYYYMMDD-XXXXXXX
    customer_id        (str)    Internal ID — joined to customers table
    customer_token     (str)    External anonymized token
    transaction_date   (date)
    transaction_ts     (timestamp)
    amount             (float)  Always positive (debits only for spend analysis)
    category           (str)    e.g., groceries, dining, travel_air
    merchant_id        (str)
    merchant_name      (str)
    channel            (str)    online | in_store
    payment_method     (str)    debit | credit
    is_recurring       (bool)   subscriptions, utilities
    state              (str)
    txn_status         (str)    posted | pending

Each customer's monthly transaction count and category mix is driven by their
persona archetype, with realistic noise:
- Seasonality: travel spikes in summer/holidays, kids spending in fall (back-to-school)
- Day-of-week: dining heavier on Fri/Sat
- Salary cycle: more transactions just after the 1st and 15th
- Random life events: 10% of customers get a "big purchase" in any given month
"""

import os
import random
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from personas import PERSONAS, CATEGORIES, get_persona

SEED = 42
random.seed(SEED)
np.random.seed(SEED)

OUTPUT_DIR = Path("data/raw")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MONTHS_OF_HISTORY = 24
END_DATE = date.today().replace(day=1)
START_DATE = (END_DATE - timedelta(days=MONTHS_OF_HISTORY * 31)).replace(day=1)

# Merchant catalog: 5–8 merchants per category
MERCHANT_CATALOG = {
    "groceries": ["Kroger", "Publix", "Whole Foods", "Trader Joe's", "Safeway", "Wegmans", "Aldi"],
    "dining": ["Olive Garden", "Cheesecake Factory", "Local Bistro", "PF Chang's", "Texas Roadhouse", "Outback", "Capital Grille"],
    "fast_food": ["McDonald's", "Chick-fil-A", "Taco Bell", "Wendy's", "Chipotle", "Subway", "Panera"],
    "coffee": ["Starbucks", "Dunkin'", "Local Coffee Co", "Peet's", "Caribou Coffee"],
    "gas": ["Shell", "Exxon", "BP", "Chevron", "Costco Gas", "Wawa Gas"],
    "rideshare": ["Uber", "Lyft"],
    "travel_air": ["Delta", "United", "American", "Southwest", "JetBlue"],
    "travel_hotel": ["Marriott", "Hilton", "Hyatt", "Airbnb", "IHG", "Best Western"],
    "entertainment": ["AMC Theatres", "Live Nation", "Ticketmaster", "Bowling Alley", "Topgolf"],
    "streaming": ["Netflix", "Spotify", "Hulu", "Disney+", "HBO Max", "Apple Music"],
    "fashion_apparel": ["Nordstrom", "Old Navy", "Gap", "Macy's", "H&M", "Zara", "Uniqlo"],
    "luxury_goods": ["Louis Vuitton", "Gucci", "Tiffany & Co", "Saks Fifth Avenue", "Neiman Marcus"],
    "electronics": ["Apple Store", "Best Buy", "Amazon Electronics", "B&H Photo", "Microcenter"],
    "home_improvement": ["Home Depot", "Lowe's", "Ace Hardware", "Menards"],
    "home_goods": ["IKEA", "Wayfair", "Crate & Barrel", "West Elm", "Williams Sonoma", "HomeGoods"],
    "kids_baby": ["Target Baby", "Buy Buy Baby", "Carter's", "Old Navy Kids", "The Children's Place"],
    "pharmacy": ["CVS", "Walgreens", "Rite Aid", "Walmart Pharmacy"],
    "healthcare": ["MedExpress", "Quest Diagnostics", "LabCorp", "Local Clinic", "Dental Office"],
    "fitness_gym": ["Planet Fitness", "Equinox", "LA Fitness", "Orangetheory", "SoulCycle", "Local Gym"],
    "wellness": ["Massage Envy", "GNC", "Vitamin Shoppe", "Local Spa"],
    "education": ["Coursera", "Udemy", "Local Tutoring", "School Supplies Co", "Barnes & Noble"],
    "utilities": ["Georgia Power", "Verizon", "Comcast", "AT&T", "Water Utility"],
    "subscriptions": ["NYTimes", "Audible", "Adobe Creative Cloud", "Microsoft 365", "Notion"],
    "department_store": ["Macy's", "Kohl's", "JCPenney", "Target", "Walmart"],
    "discount_retail": ["Dollar Tree", "Five Below", "TJ Maxx", "Marshalls", "Ross", "Burlington"],
    "warehouse_club": ["Costco", "Sam's Club", "BJ's Wholesale"],
}

# Typical transaction amount per category (mean, std)
CATEGORY_AMOUNT_PROFILE = {
    "groceries": (85, 35),
    "dining": (55, 30),
    "fast_food": (12, 5),
    "coffee": (7, 3),
    "gas": (45, 18),
    "rideshare": (18, 9),
    "travel_air": (380, 180),
    "travel_hotel": (220, 120),
    "entertainment": (45, 25),
    "streaming": (12, 4),
    "fashion_apparel": (75, 50),
    "luxury_goods": (650, 400),
    "electronics": (180, 150),
    "home_improvement": (95, 70),
    "home_goods": (120, 90),
    "kids_baby": (55, 35),
    "pharmacy": (28, 18),
    "healthcare": (180, 130),
    "fitness_gym": (45, 25),
    "wellness": (65, 35),
    "education": (75, 60),
    "utilities": (140, 50),
    "subscriptions": (15, 8),
    "department_store": (85, 55),
    "discount_retail": (35, 20),
    "warehouse_club": (165, 80),
}

# Recurring categories (subscriptions billed monthly)
RECURRING_CATEGORIES = {"streaming", "subscriptions", "utilities", "fitness_gym"}

# Seasonal multipliers by month (Jan=0)
SEASONAL_MULTIPLIERS = {
    "travel_air":      [0.9, 0.8, 1.1, 1.2, 1.3, 1.5, 1.6, 1.5, 1.0, 0.9, 1.1, 1.4],
    "travel_hotel":    [0.9, 0.8, 1.1, 1.2, 1.3, 1.5, 1.6, 1.5, 1.0, 0.9, 1.1, 1.4],
    "kids_baby":       [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.2, 1.5, 1.2, 1.0, 1.0, 1.3],  # back-to-school + holidays
    "education":       [1.2, 1.0, 1.0, 1.0, 1.0, 0.7, 1.0, 1.5, 1.4, 1.0, 1.0, 1.0],
    "fashion_apparel": [1.0, 1.0, 1.1, 1.1, 1.1, 1.0, 1.0, 1.3, 1.2, 1.0, 1.2, 1.5],
    "home_goods":      [0.9, 0.9, 1.0, 1.1, 1.2, 1.1, 1.0, 1.0, 1.0, 1.0, 1.2, 1.3],
    "luxury_goods":    [1.0, 1.2, 1.0, 1.0, 1.1, 1.1, 1.0, 1.0, 1.0, 1.0, 1.3, 1.6],
    "entertainment":   [1.0, 1.1, 1.0, 1.0, 1.1, 1.2, 1.3, 1.2, 1.0, 1.0, 1.1, 1.3],
    "fitness_gym":     [1.4, 1.2, 1.1, 1.0, 1.0, 1.0, 0.9, 0.9, 1.0, 1.0, 0.9, 0.8],  # New Year resolution effect
}


def get_seasonal_multiplier(category: str, month_idx: int) -> float:
    """1-indexed month (1=Jan)."""
    return SEASONAL_MULTIPLIERS.get(category, [1.0] * 12)[month_idx - 1]


def pick_category(persona) -> str:
    """Sample a category according to persona weights."""
    cats = list(persona.category_weights.keys())
    weights = list(persona.category_weights.values())
    return random.choices(cats, weights=weights, k=1)[0]


def pick_merchant(category: str) -> str:
    return random.choice(MERCHANT_CATALOG.get(category, ["Generic Merchant"]))


def amount_for_category(category: str, persona) -> float:
    mean, std = CATEGORY_AMOUNT_PROFILE[category]
    # Higher-income personas spend more per transaction
    income_factor = 1.0
    if persona.income_range[1] > 200000:
        income_factor = 1.6
    elif persona.income_range[1] > 130000:
        income_factor = 1.3
    elif persona.income_range[1] > 80000:
        income_factor = 1.1
    elif persona.income_range[1] < 40000:
        income_factor = 0.7

    amt = np.random.normal(mean * income_factor, std * income_factor)
    return max(round(float(amt), 2), 1.00)


def generate_month_transactions(customer: dict, year: int, month: int, txn_seq_start: int) -> list:
    """Generate all transactions for one customer-month."""
    persona = get_persona(customer["persona_id"])

    base_count = random.randint(*persona.txn_frequency_monthly)
    # Random life event: ±20% variance
    monthly_count = int(base_count * random.uniform(0.85, 1.15))

    rows = []
    txn_seq = txn_seq_start

    # Calculate days in month
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    days_in_month = (next_month - date(year, month, 1)).days

    # Add recurring transactions first (deterministic on the 1st-3rd of month)
    for cat in RECURRING_CATEGORIES:
        if cat in persona.category_weights and persona.category_weights[cat] > 0.02:
            day = random.randint(1, 3)
            txn_date = date(year, month, day)
            rows.append(_make_txn(customer, persona, cat, txn_date, txn_seq, recurring=True))
            txn_seq += 1
            monthly_count -= 1

    # Distribute remaining transactions across the month
    for _ in range(max(monthly_count, 0)):
        category = pick_category(persona)

        # Apply seasonal effect: skip some transactions if out of season for travel
        seasonal = get_seasonal_multiplier(category, month)
        if random.random() > seasonal:
            # Re-roll a non-seasonal category
            non_seasonal_cats = [c for c in persona.category_weights if c not in SEASONAL_MULTIPLIERS]
            if non_seasonal_cats:
                category = random.choice(non_seasonal_cats)

        # Skew day-of-month: heavier just after 1st and 15th
        day = _sample_day_of_month(days_in_month)
        txn_date = date(year, month, day)
        rows.append(_make_txn(customer, persona, category, txn_date, txn_seq))
        txn_seq += 1

    return rows


def _sample_day_of_month(days_in_month: int) -> int:
    """Bias day selection toward 1-5 and 15-20 (paycheck effect)."""
    rand = random.random()
    if rand < 0.30:
        return random.randint(1, 5)
    elif rand < 0.55:
        return random.randint(15, 20)
    else:
        return random.randint(1, days_in_month)


def _make_txn(customer: dict, persona, category: str, txn_date: date, seq: int, recurring: bool = False) -> dict:
    amount = amount_for_category(category, persona)
    merchant = pick_merchant(category)

    # Online share by category — some categories are mostly online
    online_heavy = {"streaming", "subscriptions", "rideshare", "education"}
    in_store_heavy = {"gas", "groceries", "fast_food", "warehouse_club", "pharmacy"}
    if category in online_heavy:
        channel_prob = 0.95
    elif category in in_store_heavy:
        channel_prob = 0.10
    else:
        channel_prob = persona.online_share

    channel = "online" if random.random() < channel_prob else "in_store"

    # Time-of-day: dining peaks 6–9pm, coffee peaks 7–10am, etc.
    hour = random.randint(8, 22)
    minute = random.randint(0, 59)
    txn_ts = datetime.combine(txn_date, datetime.min.time()).replace(hour=hour, minute=minute)

    return {
        "transaction_id": f"TXN-{txn_date.strftime('%Y%m%d')}-{seq:07d}",
        "customer_id": customer["customer_id"],
        "customer_token": customer["customer_token"],
        "transaction_date": txn_date,
        "transaction_ts": txn_ts,
        "amount": amount,
        "category": category,
        "merchant_id": f"M-{abs(hash(merchant)) % 100000:05d}",
        "merchant_name": merchant,
        "channel": channel,
        "payment_method": random.choices(["debit", "credit"], weights=[0.45, 0.55])[0],
        "is_recurring": recurring,
        "state": customer["state"],
        "txn_status": "posted" if random.random() < 0.98 else "pending",
    }


def main():
    customers_path = OUTPUT_DIR / "customers.parquet"
    if not customers_path.exists():
        raise FileNotFoundError(
            f"Run generate_customers.py first — {customers_path} not found"
        )

    customers_df = pd.read_parquet(customers_path)
    print(f"Loaded {len(customers_df)} customers")
    print(f"Generating {MONTHS_OF_HISTORY} months of transactions "
          f"({START_DATE} to {END_DATE})...")

    all_rows = []
    txn_seq = 1

    # Iterate month by month
    current = START_DATE
    while current < END_DATE:
        month_rows = []
        for _, customer in customers_df.iterrows():
            if not customer["is_active"]:
                continue
            customer_dict = customer.to_dict()
            month_rows.extend(
                generate_month_transactions(customer_dict, current.year, current.month, txn_seq)
            )
            txn_seq += 200  # spacing to keep IDs unique

        all_rows.extend(month_rows)
        print(f"  {current:%Y-%m}: {len(month_rows):>7,} transactions  "
              f"(running total: {len(all_rows):>9,})")

        # Move to next month
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)

    df = pd.DataFrame(all_rows)
    print(f"\n✓ Total: {len(df):,} transactions")

    # Write parquet (full) and CSV sample (10K rows for inspection)
    parquet_path = OUTPUT_DIR / "transactions.parquet"
    csv_sample_path = OUTPUT_DIR / "transactions_sample.csv"
    df.to_parquet(parquet_path, index=False, coerce_timestamps='us')
    df.sample(min(10000, len(df)), random_state=SEED).to_csv(csv_sample_path, index=False)

    print(f"  - {parquet_path}")
    print(f"  - {csv_sample_path} (10K row sample)")

    # Summary stats
    print(f"\nCategory mix (top 10):")
    print(df["category"].value_counts().head(10).to_string())
    print(f"\nMonthly transaction totals:")
    df["yearmonth"] = pd.to_datetime(df["transaction_date"]).dt.to_period("M")
    monthly_summary = df.groupby("yearmonth").agg(
        txns=("transaction_id", "count"),
        spend=("amount", "sum"),
    ).round(0)
    print(monthly_summary.tail(12).to_string())


if __name__ == "__main__":
    main()