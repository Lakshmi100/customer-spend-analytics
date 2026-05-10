"""
Coupon catalog — the supply side of the recommendation engine.

In a real bank-merchant partnership, this catalog would come from
the merchant API or the bank's offers platform. For our portfolio
project, we synthesize a realistic catalog spanning all spend
categories from our personas.

Each coupon has:
    - coupon_id              unique identifier
    - merchant_name          which brand offers it
    - category               maps to our spend categories
    - discount_value         percent or dollar off
    - discount_display       human-readable label
    - min_spend              minimum spend to qualify
    - tier                   value | mainstream | premium | luxury
    - title                  marketing copy
"""

from dataclasses import dataclass, asdict
from typing import List
import pandas as pd


@dataclass
class Coupon:
    coupon_id: str
    merchant_name: str
    category: str
    discount_value: float
    discount_display: str
    min_spend: float
    tier: str
    title: str


COUPON_CATALOG: List[Coupon] = [
    # === GROCERIES ===
    Coupon("CPN-G001", "Kroger",        "groceries", 0.10, "10% off",     50,  "value",      "Save 10% on your weekly Kroger run"),
    Coupon("CPN-G002", "Whole Foods",   "groceries", 0.15, "15% off",     75,  "premium",    "Whole Foods premium produce — 15% off $75+"),
    Coupon("CPN-G003", "Costco",        "warehouse_club", 25, "$25 off",  150, "value",      "$25 off your next Costco haul"),

    # === DINING ===
    Coupon("CPN-D001", "Cheesecake Factory", "dining",     0.20, "20% off",  40,  "mainstream", "20% off dinner for two"),
    Coupon("CPN-D002", "Capital Grille",     "dining",     50,   "$50 off",  150, "luxury",     "$50 off your next steakhouse experience"),
    Coupon("CPN-D003", "Olive Garden",       "dining",     15,   "$15 off",  40,  "value",      "$15 off family dinner"),

    # === FAST FOOD / COFFEE ===
    Coupon("CPN-F001", "Chipotle",   "fast_food", 5,    "$5 off",  15, "value",      "Free guac + $5 off your next bowl"),
    Coupon("CPN-F002", "Starbucks",  "coffee",    0.20, "20% off", 10, "mainstream", "20% off your morning Starbucks"),
    Coupon("CPN-F003", "McDonald's", "fast_food", 3,    "$3 off",  10, "value",      "$3 off any combo meal"),

    # === TRAVEL ===
    Coupon("CPN-T001", "Delta Airlines",   "travel_air",   75,  "$75 off",  300, "mainstream", "$75 off your next Delta flight"),
    Coupon("CPN-T002", "Marriott Bonvoy",  "travel_hotel", 100, "$100 off", 400, "premium",    "$100 off a 3-night Marriott stay"),
    Coupon("CPN-T003", "Airbnb",           "travel_hotel", 50,  "$50 off",  250, "mainstream", "$50 off your next Airbnb getaway"),
    Coupon("CPN-T004", "Hilton Honors",    "travel_hotel", 0.15,"15% off",  300, "premium",    "15% off Hilton premium stays"),

    # === ENTERTAINMENT / SUBSCRIPTIONS ===
    Coupon("CPN-E001", "AMC Theatres",    "entertainment", 0.25, "25% off",  20, "mainstream", "25% off movie tickets this weekend"),
    Coupon("CPN-E002", "Spotify Premium", "streaming",     3,    "$3 off",   10, "mainstream", "$3 off Spotify Premium for 6 months"),
    Coupon("CPN-E003", "Live Nation",     "entertainment", 25,   "$25 off",  100,"mainstream", "$25 off concert tickets"),

    # === FASHION / LUXURY ===
    Coupon("CPN-L001", "Nordstrom",       "fashion_apparel", 0.20, "20% off", 100, "premium",    "20% off premium fashion at Nordstrom"),
    Coupon("CPN-L002", "Louis Vuitton",   "luxury_goods",    0.10, "10% off", 1000,"luxury",     "Exclusive: 10% off Louis Vuitton selections"),
    Coupon("CPN-L003", "Tiffany & Co",    "luxury_goods",    150,  "$150 off",750, "luxury",     "$150 off Tiffany jewelry"),
    Coupon("CPN-L004", "Old Navy",        "fashion_apparel", 0.30, "30% off", 50,  "value",      "30% off your Old Navy basics"),

    # === ELECTRONICS / HOME ===
    Coupon("CPN-X001", "Apple Store",     "electronics",      75,  "$75 off",  400, "premium",    "$75 off AirPods or Apple Watch"),
    Coupon("CPN-X002", "Best Buy",        "electronics",      0.15,"15% off",  200, "mainstream", "15% off TVs and appliances"),
    Coupon("CPN-H001", "Home Depot",      "home_improvement", 25,  "$25 off",  150, "mainstream", "$25 off home improvement project"),
    Coupon("CPN-H002", "IKEA",            "home_goods",       0.20,"20% off",  100, "mainstream", "20% off your next IKEA visit"),

    # === KIDS / FAMILY ===
    Coupon("CPN-K001", "Carter's",        "kids_baby", 0.25, "25% off", 40, "mainstream", "25% off kids essentials at Carter's"),
    Coupon("CPN-K002", "Buy Buy Baby",    "kids_baby", 20,   "$20 off", 75, "mainstream", "$20 off baby gear and supplies"),

    # === HEALTH / WELLNESS ===
    Coupon("CPN-W001", "Equinox",         "fitness_gym", 0.30, "30% off", 100, "premium",    "30% off your next month at Equinox"),
    Coupon("CPN-W002", "Planet Fitness",  "fitness_gym", 5,    "$5 off",  15,  "value",      "$5 off your monthly Planet Fitness"),
    Coupon("CPN-W003", "GNC",             "wellness",    0.15, "15% off", 50,  "mainstream", "15% off vitamins and supplements"),
    Coupon("CPN-W004", "CVS",             "pharmacy",    0.10, "10% off", 25,  "value",      "10% off your CVS pharmacy items"),

    # === GAS / RIDESHARE ===
    Coupon("CPN-R001", "Uber",            "rideshare", 8,   "$8 off",   30, "mainstream", "$8 off your next 3 Uber rides"),
    Coupon("CPN-R002", "Lyft",            "rideshare", 5,   "$5 off",   20, "mainstream", "$5 off rides this weekend"),
    Coupon("CPN-R003", "Shell Gas",       "gas",       0.05,"5% cashback", 30, "value",   "5% cashback on Shell fill-ups"),
]


def get_catalog_df() -> pd.DataFrame:
    """Return the catalog as a DataFrame for the ranker."""
    return pd.DataFrame([asdict(c) for c in COUPON_CATALOG])


def get_coupon(coupon_id: str) -> Coupon:
    for c in COUPON_CATALOG:
        if c.coupon_id == coupon_id:
            return c
    raise ValueError(f"Coupon {coupon_id} not found")


if __name__ == "__main__":
    df = get_catalog_df()
    print(f"Coupon catalog: {len(df)} offers across {df['category'].nunique()} categories\n")
    print("Coverage by category:")
    print(df.groupby("category").size().sort_values(ascending=False).to_string())
    print("\nCoverage by tier:")
    print(df.groupby("tier").size().to_string())
