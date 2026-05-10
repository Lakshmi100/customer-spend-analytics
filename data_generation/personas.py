"""
Customer personas for ABC Bank synthetic data generation.

Each persona defines:
- Demographics (age range, income range, family situation)
- Spend behavior (category weights, monthly spend range, transaction frequency)
- Geographic preference (urban/suburban/rural)
- Channel preferences (in-store vs online)

These 20 personas cover the full spectrum of US banking customers and are
designed to produce learnable patterns for ML segmentation and coupon
recommendation models.
"""

from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass
class Persona:
    persona_id: str
    name: str
    age_range: Tuple[int, int]
    income_range: Tuple[int, int]
    family_status: str  # single, married_no_kids, married_with_kids, divorced, widowed
    num_dependents: Tuple[int, int]
    geography: str  # urban, suburban, rural
    monthly_spend_range: Tuple[int, int]
    txn_frequency_monthly: Tuple[int, int]  # min, max transactions per month
    online_share: float  # 0.0 to 1.0 — share of txns that are online
    category_weights: Dict[str, float] = field(default_factory=dict)
    description: str = ""


# Spend categories used across all personas
CATEGORIES = [
    "groceries", "dining", "fast_food", "coffee", "gas", "rideshare",
    "travel_air", "travel_hotel", "entertainment", "streaming",
    "fashion_apparel", "luxury_goods", "electronics", "home_improvement",
    "home_goods", "kids_baby", "pharmacy", "healthcare", "fitness_gym",
    "wellness", "education", "utilities", "subscriptions",
    "department_store", "discount_retail", "warehouse_club",
]


PERSONAS = [
    Persona(
        persona_id="P01",
        name="College Student Sasha",
        age_range=(21, 24),
        income_range=(12000, 22000),
        family_status="single",
        num_dependents=(0, 0),
        geography="urban",
        monthly_spend_range=(800, 1400),
        txn_frequency_monthly=(40, 70),
        online_share=0.55,
        category_weights={
            "fast_food": 0.18, "coffee": 0.12, "rideshare": 0.10,
            "streaming": 0.06, "fashion_apparel": 0.10, "education": 0.10,
            "groceries": 0.08, "entertainment": 0.08, "utilities": 0.08,
            "subscriptions": 0.05, "discount_retail": 0.05,
        },
        description="Cash-strapped student, lots of small transactions, food delivery heavy",
    ),
    Persona(
        persona_id="P02",
        name="Entry-Level Alex",
        age_range=(24, 28),
        income_range=(45000, 60000),
        family_status="single",
        num_dependents=(0, 0),
        geography="urban",
        monthly_spend_range=(2200, 3200),
        txn_frequency_monthly=(50, 80),
        online_share=0.45,
        category_weights={
            "dining": 0.15, "coffee": 0.10, "fitness_gym": 0.08,
            "groceries": 0.10, "fashion_apparel": 0.08, "subscriptions": 0.07,
            "rideshare": 0.06, "travel_air": 0.06, "travel_hotel": 0.05,
            "entertainment": 0.08, "utilities": 0.08, "streaming": 0.05,
            "wellness": 0.04,
        },
        description="Young professional, lifestyle spending, gym + brunches",
    ),
    Persona(
        persona_id="P03",
        name="Tech Bro Tyler",
        age_range=(26, 32),
        income_range=(115000, 165000),
        family_status="single",
        num_dependents=(0, 0),
        geography="urban",
        monthly_spend_range=(5500, 8500),
        txn_frequency_monthly=(60, 100),
        online_share=0.55,
        category_weights={
            "electronics": 0.12, "dining": 0.15, "fitness_gym": 0.08,
            "travel_air": 0.10, "travel_hotel": 0.08, "fashion_apparel": 0.08,
            "entertainment": 0.07, "subscriptions": 0.06, "coffee": 0.06,
            "luxury_goods": 0.06, "rideshare": 0.05, "wellness": 0.04,
            "groceries": 0.05,
        },
        description="High-income single, premium everything, frequent travel",
    ),
    Persona(
        persona_id="P04",
        name="Newlyweds Priya & Raj",
        age_range=(27, 32),
        income_range=(125000, 160000),
        family_status="married_no_kids",
        num_dependents=(0, 0),
        geography="suburban",
        monthly_spend_range=(5000, 7000),
        txn_frequency_monthly=(55, 85),
        online_share=0.50,
        category_weights={
            "home_goods": 0.15, "groceries": 0.12, "dining": 0.12,
            "travel_air": 0.08, "travel_hotel": 0.07, "home_improvement": 0.08,
            "streaming": 0.05, "fashion_apparel": 0.08, "entertainment": 0.06,
            "utilities": 0.07, "subscriptions": 0.05, "department_store": 0.07,
        },
        description="Setting up first home, IKEA/Wayfair/Target, weekend getaways",
    ),
    Persona(
        persona_id="P05",
        name="New Parent Maya",
        age_range=(30, 35),
        income_range=(68000, 88000),
        family_status="married_with_kids",
        num_dependents=(1, 1),
        geography="suburban",
        monthly_spend_range=(3500, 5000),
        txn_frequency_monthly=(50, 80),
        online_share=0.65,
        category_weights={
            "kids_baby": 0.20, "groceries": 0.18, "pharmacy": 0.10,
            "healthcare": 0.08, "utilities": 0.07, "gas": 0.06,
            "discount_retail": 0.08, "home_goods": 0.06, "subscriptions": 0.05,
            "streaming": 0.04, "fast_food": 0.04, "warehouse_club": 0.04,
        },
        description="Diaper-and-formula era, high online ordering, less dining out",
    ),
    Persona(
        persona_id="P06",
        name="Soccer Mom Linda",
        age_range=(35, 42),
        income_range=(85000, 110000),
        family_status="married_with_kids",
        num_dependents=(2, 3),
        geography="suburban",
        monthly_spend_range=(4500, 6500),
        txn_frequency_monthly=(60, 95),
        online_share=0.40,
        category_weights={
            "groceries": 0.20, "warehouse_club": 0.10, "kids_baby": 0.10,
            "gas": 0.08, "fast_food": 0.07, "education": 0.06,
            "entertainment": 0.06, "fashion_apparel": 0.07, "pharmacy": 0.05,
            "department_store": 0.07, "utilities": 0.07, "dining": 0.07,
        },
        description="Bulk shopping, kids' activities, Costco runs, minivan gas",
    ),
    Persona(
        persona_id="P07",
        name="DINK Sam",
        age_range=(32, 40),
        income_range=(170000, 220000),
        family_status="married_no_kids",
        num_dependents=(0, 0),
        geography="urban",
        monthly_spend_range=(7000, 10000),
        txn_frequency_monthly=(65, 95),
        online_share=0.50,
        category_weights={
            "dining": 0.18, "travel_air": 0.12, "travel_hotel": 0.10,
            "entertainment": 0.10, "fitness_gym": 0.07, "fashion_apparel": 0.10,
            "luxury_goods": 0.07, "wellness": 0.06, "coffee": 0.05,
            "subscriptions": 0.05, "groceries": 0.06, "rideshare": 0.04,
        },
        description="Experiences over things, frequent fine dining, premium travel",
    ),
    Persona(
        persona_id="P08",
        name="Single Dad Marcus",
        age_range=(36, 44),
        income_range=(58000, 78000),
        family_status="divorced",
        num_dependents=(1, 2),
        geography="suburban",
        monthly_spend_range=(2800, 4000),
        txn_frequency_monthly=(45, 70),
        online_share=0.35,
        category_weights={
            "groceries": 0.18, "fast_food": 0.10, "gas": 0.08,
            "kids_baby": 0.08, "utilities": 0.10, "entertainment": 0.07,
            "discount_retail": 0.10, "pharmacy": 0.05, "dining": 0.06,
            "home_goods": 0.05, "fashion_apparel": 0.06, "subscriptions": 0.04,
            "streaming": 0.03,
        },
        description="Variable spending tied to custody schedule, value-focused",
    ),
    Persona(
        persona_id="P09",
        name="Stay-at-Home Parent Jenna",
        age_range=(33, 40),
        income_range=(0, 0),  # Personal income 0, household high
        family_status="married_with_kids",
        num_dependents=(2, 4),
        geography="suburban",
        monthly_spend_range=(5500, 7500),
        txn_frequency_monthly=(70, 110),
        online_share=0.55,
        category_weights={
            "groceries": 0.22, "kids_baby": 0.15, "warehouse_club": 0.10,
            "education": 0.07, "pharmacy": 0.06, "department_store": 0.08,
            "gas": 0.06, "home_goods": 0.06, "discount_retail": 0.07,
            "fast_food": 0.04, "subscriptions": 0.04, "utilities": 0.05,
        },
        description="Household manager, huge grocery + warehouse club spend",
    ),
    Persona(
        persona_id="P10",
        name="Climbing Career Aisha",
        age_range=(38, 45),
        income_range=(130000, 165000),
        family_status="divorced",
        num_dependents=(1, 1),
        geography="suburban",
        monthly_spend_range=(4500, 6500),
        txn_frequency_monthly=(55, 85),
        online_share=0.50,
        category_weights={
            "groceries": 0.13, "fashion_apparel": 0.12, "education": 0.08,
            "dining": 0.10, "kids_baby": 0.08, "travel_air": 0.06,
            "fitness_gym": 0.07, "electronics": 0.06, "wellness": 0.05,
            "department_store": 0.07, "gas": 0.05, "subscriptions": 0.05,
            "entertainment": 0.05, "utilities": 0.03,
        },
        description="Single mom executive, professional wardrobe, teen tech needs",
    ),
    Persona(
        persona_id="P11",
        name="Empty Nesters Bob & Susan",
        age_range=(52, 60),
        income_range=(150000, 185000),
        family_status="married_no_kids",  # kids in college, not at home
        num_dependents=(0, 0),
        geography="suburban",
        monthly_spend_range=(6000, 8500),
        txn_frequency_monthly=(50, 80),
        online_share=0.45,
        category_weights={
            "travel_air": 0.15, "travel_hotel": 0.13, "dining": 0.13,
            "home_improvement": 0.10, "entertainment": 0.08, "groceries": 0.08,
            "education": 0.07, "wellness": 0.05, "fashion_apparel": 0.06,
            "subscriptions": 0.04, "home_goods": 0.06, "utilities": 0.05,
        },
        description="Big travel spenders, college tuition transfers, home upgrades",
    ),
    Persona(
        persona_id="P12",
        name="Mid-Career Manager Dev",
        age_range=(45, 52),
        income_range=(190000, 240000),
        family_status="married_with_kids",
        num_dependents=(1, 3),
        geography="suburban",
        monthly_spend_range=(7000, 10000),
        txn_frequency_monthly=(70, 100),
        online_share=0.45,
        category_weights={
            "groceries": 0.13, "home_improvement": 0.10, "education": 0.10,
            "dining": 0.10, "kids_baby": 0.06, "travel_air": 0.06,
            "travel_hotel": 0.05, "entertainment": 0.06, "fashion_apparel": 0.07,
            "gas": 0.05, "warehouse_club": 0.07, "utilities": 0.06,
            "electronics": 0.05, "subscriptions": 0.04,
        },
        description="High earner with teens, big home/family/education spend",
    ),
    Persona(
        persona_id="P13",
        name="Frugal Saver Eleanor",
        age_range=(48, 56),
        income_range=(65000, 80000),
        family_status="divorced",
        num_dependents=(0, 0),
        geography="suburban",
        monthly_spend_range=(1800, 2800),
        txn_frequency_monthly=(35, 55),
        online_share=0.30,
        category_weights={
            "groceries": 0.22, "discount_retail": 0.15, "utilities": 0.12,
            "gas": 0.08, "pharmacy": 0.07, "dining": 0.05,
            "home_goods": 0.05, "fashion_apparel": 0.05, "healthcare": 0.06,
            "entertainment": 0.04, "streaming": 0.03, "subscriptions": 0.03,
            "warehouse_club": 0.05,
        },
        description="Penny-pincher, generic brands, minimal discretionary spend",
    ),
    Persona(
        persona_id="P14",
        name="Healthcare Worker Maria",
        age_range=(40, 48),
        income_range=(78000, 98000),
        family_status="married_with_kids",
        num_dependents=(1, 2),
        geography="suburban",
        monthly_spend_range=(3500, 4800),
        txn_frequency_monthly=(50, 75),
        online_share=0.40,
        category_weights={
            "groceries": 0.18, "gas": 0.12, "fashion_apparel": 0.07,
            "kids_baby": 0.07, "pharmacy": 0.08, "fast_food": 0.07,
            "utilities": 0.08, "dining": 0.06, "entertainment": 0.05,
            "department_store": 0.06, "healthcare": 0.05, "education": 0.04,
            "subscriptions": 0.04, "streaming": 0.03,
        },
        description="Long commute (high gas), uniforms, family staples",
    ),
    Persona(
        persona_id="P15",
        name="Pre-Retiree James",
        age_range=(58, 64),
        income_range=(120000, 155000),
        family_status="married_no_kids",
        num_dependents=(0, 0),
        geography="suburban",
        monthly_spend_range=(5000, 7000),
        txn_frequency_monthly=(45, 70),
        online_share=0.40,
        category_weights={
            "travel_air": 0.12, "travel_hotel": 0.10, "healthcare": 0.10,
            "home_improvement": 0.10, "dining": 0.10, "groceries": 0.10,
            "entertainment": 0.07, "wellness": 0.06, "subscriptions": 0.05,
            "fashion_apparel": 0.05, "utilities": 0.05, "pharmacy": 0.05,
            "home_goods": 0.05,
        },
        description="Planning retirement, healthcare ramp-up, travel & hobbies",
    ),
    Persona(
        persona_id="P16",
        name="Active Retiree Carol",
        age_range=(65, 72),
        income_range=(48000, 68000),
        family_status="widowed",
        num_dependents=(0, 0),
        geography="suburban",
        monthly_spend_range=(2500, 3800),
        txn_frequency_monthly=(40, 65),
        online_share=0.30,
        category_weights={
            "groceries": 0.18, "pharmacy": 0.12, "healthcare": 0.10,
            "home_goods": 0.08, "dining": 0.08, "utilities": 0.10,
            "department_store": 0.07, "entertainment": 0.06, "gas": 0.05,
            "wellness": 0.05, "subscriptions": 0.04, "streaming": 0.03,
            "discount_retail": 0.04,
        },
        description="Pharmacy regular, gardening, gifts to grandkids",
    ),
    Persona(
        persona_id="P17",
        name="Snowbird Couple Ron & Pat",
        age_range=(68, 75),
        income_range=(85000, 110000),
        family_status="married_no_kids",
        num_dependents=(0, 0),
        geography="suburban",
        monthly_spend_range=(4000, 5800),
        txn_frequency_monthly=(50, 75),
        online_share=0.35,
        category_weights={
            "travel_air": 0.10, "travel_hotel": 0.08, "groceries": 0.13,
            "dining": 0.12, "healthcare": 0.10, "gas": 0.08,
            "utilities": 0.10, "entertainment": 0.07, "pharmacy": 0.06,
            "home_goods": 0.05, "wellness": 0.05, "subscriptions": 0.03,
            "fashion_apparel": 0.03,
        },
        description="Two-home lifestyle, FL/AZ winters, dining and leisure",
    ),
    Persona(
        persona_id="P18",
        name="Side Hustler Jordan",
        age_range=(30, 38),
        income_range=(58000, 75000),  # W2 only
        family_status="single",
        num_dependents=(0, 0),
        geography="urban",
        monthly_spend_range=(3500, 5000),
        txn_frequency_monthly=(70, 110),
        online_share=0.65,
        category_weights={
            "subscriptions": 0.10, "electronics": 0.10, "dining": 0.10,
            "rideshare": 0.08, "coffee": 0.08, "fast_food": 0.07,
            "groceries": 0.08, "fitness_gym": 0.05, "entertainment": 0.06,
            "fashion_apparel": 0.07, "utilities": 0.07, "streaming": 0.05,
            "travel_air": 0.05, "wellness": 0.04,
        },
        description="Multiple income streams, lots of business-adjacent expenses",
    ),
    Persona(
        persona_id="P19",
        name="Fitness Enthusiast Kai",
        age_range=(27, 33),
        income_range=(78000, 95000),
        family_status="single",
        num_dependents=(0, 0),
        geography="urban",
        monthly_spend_range=(3000, 4500),
        txn_frequency_monthly=(55, 85),
        online_share=0.50,
        category_weights={
            "fitness_gym": 0.15, "wellness": 0.12, "groceries": 0.15,
            "fashion_apparel": 0.10, "dining": 0.08, "subscriptions": 0.08,
            "healthcare": 0.05, "coffee": 0.05, "entertainment": 0.05,
            "travel_air": 0.05, "utilities": 0.06, "streaming": 0.04,
            "rideshare": 0.02,
        },
        description="Whole Foods + premium gym + supplements + athleisure",
    ),
    Persona(
        persona_id="P20",
        name="Luxury Seeker Vanessa",
        age_range=(40, 50),
        income_range=(260000, 340000),
        family_status="married_with_kids",
        num_dependents=(0, 2),
        geography="urban",
        monthly_spend_range=(12000, 18000),
        txn_frequency_monthly=(70, 110),
        online_share=0.45,
        category_weights={
            "luxury_goods": 0.20, "fashion_apparel": 0.15, "travel_air": 0.10,
            "travel_hotel": 0.10, "dining": 0.12, "wellness": 0.06,
            "entertainment": 0.07, "home_goods": 0.06, "fitness_gym": 0.05,
            "kids_baby": 0.04, "subscriptions": 0.03, "groceries": 0.02,
        },
        description="Designer everything, international travel, premium services",
    ),
]


def get_persona(persona_id: str) -> Persona:
    """Look up a persona by ID."""
    for p in PERSONAS:
        if p.persona_id == persona_id:
            return p
    raise ValueError(f"Unknown persona_id: {persona_id}")


if __name__ == "__main__":
    # Sanity check: all category weights sum to ~1.0
    print(f"{'Persona':<35} {'Weight Sum':>12}")
    print("-" * 50)
    for p in PERSONAS:
        total = sum(p.category_weights.values())
        flag = "✓" if 0.95 <= total <= 1.05 else "✗ FIX"
        print(f"{p.name:<35} {total:>10.3f} {flag}")