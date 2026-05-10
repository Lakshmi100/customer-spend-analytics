"""
FastAPI service for the ABC Bank Coupon Recommendation Engine.

Exposes the ML recommender as REST endpoints with auto-generated OpenAPI docs.

Run from project root:
    uvicorn api.main:app --reload --port 8000

Then visit:
    http://localhost:8000          → API root
    http://localhost:8000/docs     → interactive Swagger UI
    http://localhost:8000/redoc    → alternative API docs

Example calls:
    curl http://localhost:8000/health
    curl http://localhost:8000/customers/random
    curl http://localhost:8000/coupons/7c4ba8bb6ad29427
    curl http://localhost:8000/coupons/7c4ba8bb6ad29427?top_n=5
"""

from datetime import datetime
from functools import lru_cache
from typing import List, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ml.predict import get_coupons
from ml.snowflake_io import query_snowflake


# ============================================================================
# Pydantic response models — these auto-generate OpenAPI schemas
# ============================================================================

class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    snowflake_connected: bool
    customer_360_rows: Optional[int] = None
    error: Optional[str] = None


class CouponSignals(BaseModel):
    affinity_index: float = Field(..., description="How much customer over-indexes on this category vs population avg")
    days_since_last_txn: int = Field(..., description="Days since customer last transacted in this category")
    wallet_share: float = Field(..., description="What fraction of customer's wallet goes to this category")


class ScoreComponents(BaseModel):
    affinity_score: float = Field(..., description="Log-scaled customer affinity (0-1)")
    recency_score: float = Field(..., description="Exponential recency decay (0-1)")
    cluster_score: float = Field(..., description="Cluster-level peer signal (0-1)")


class CouponRecommendation(BaseModel):
    coupon_id: str
    merchant_name: str
    category: str
    tier: str = Field(..., description="value | mainstream | premium | luxury")
    title: str
    discount_display: str
    score: float = Field(..., description="Composite recommendation score 0-1, higher is better")
    components: ScoreComponents
    signals: CouponSignals
    reasoning: str = Field(..., description="Human-readable explanation")


class CouponResponse(BaseModel):
    customer_token: str
    customer_persona: str
    customer_cluster: int
    recommendations: List[CouponRecommendation]
    served_at: datetime


class CustomerProfile(BaseModel):
    customer_token: str
    persona_name: str
    age_band: str
    income_band: str
    family_status: str
    state: str
    account_type: str
    rfm_total_score: int
    total_spend: float
    total_transactions: int
    top_category_1: str
    top_category_2: Optional[str]
    top_category_3: Optional[str]


class ClusterSummary(BaseModel):
    cluster: int
    size: int
    size_pct: float
    signature_persona: str
    signature_lift: float


# ============================================================================
# FastAPI app + middleware
# ============================================================================

app = FastAPI(
    title="ABC Bank — Coupon Recommendation Engine",
    description=(
        "Personalized digital coupon recommendations for ABC Bank customers, "
        "powered by KMeans segmentation + category affinity scoring."
    ),
    version="1.0.0",
)

# CORS so Streamlit (or any frontend) can call this
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Cached data loads — the API process holds these in memory across requests
# ============================================================================

@lru_cache(maxsize=1)
def _customer_meta_cache() -> pd.DataFrame:
    """Cached customer cluster + persona lookup."""
    from ml.coupon_ranker import load_customer_clusters
    return load_customer_clusters()


# ============================================================================
# Endpoints
# ============================================================================

@app.get("/", tags=["meta"])
def root():
    return {
        "service": "ABC Bank Coupon Recommendation Engine",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": [
            "/health",
            "/coupons/{customer_token}",
            "/customers/{customer_token}/profile",
            "/customers/random",
            "/stats/clusters",
        ],
    }


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health():
    """Verify Snowflake connectivity and customer_360 access."""
    try:
        df = query_snowflake("SELECT COUNT(*) AS n FROM MARTS.CUSTOMER_360")
        return HealthResponse(
            status="ok",
            timestamp=datetime.utcnow(),
            snowflake_connected=True,
            customer_360_rows=int(df["n"].iloc[0]),
        )
    except Exception as e:
        return HealthResponse(
            status="degraded",
            timestamp=datetime.utcnow(),
            snowflake_connected=False,
            error=str(e),
        )


@app.get(
    "/coupons/{customer_token}",
    response_model=CouponResponse,
    tags=["recommender"],
    summary="Get personalized coupon recommendations",
)
def get_coupon_recommendations(
    customer_token: str,
    top_n: int = Query(3, ge=1, le=10, description="How many coupons to return (1-10)"),
):
    """
    Returns top N coupon recommendations for a customer, ranked by composite score.

    The score combines:
    - **affinity** (50%): customer's spending intensity in the coupon's category
    - **recency** (30%): how recently they transacted in that category
    - **cluster** (20%): preference signal from the customer's behavioral cluster
    """
    try:
        recs = get_coupons(customer_token, top_n=top_n)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")

    if not recs:
        raise HTTPException(
            status_code=404,
            detail=f"No coupons matched for customer {customer_token}",
        )

    return CouponResponse(
        customer_token=customer_token,
        customer_persona=recs[0]["_meta"]["customer_persona"],
        customer_cluster=recs[0]["_meta"]["customer_cluster"],
        recommendations=[
            CouponRecommendation(
                coupon_id=r["coupon_id"],
                merchant_name=r["merchant_name"],
                category=r["category"],
                tier=r["tier"],
                title=r["title"],
                discount_display=r["discount_display"],
                score=r["score"],
                components=ScoreComponents(**r["components"]),
                signals=CouponSignals(**r["signals"]),
                reasoning=r["reasoning"],
            )
            for r in recs
        ],
        served_at=datetime.utcnow(),
    )


@app.get(
    "/customers/{customer_token}/profile",
    response_model=CustomerProfile,
    tags=["customer"],
    summary="Get the customer 360 profile",
)
def customer_profile(customer_token: str):
    """Returns the analytics-safe customer profile from MARTS.CUSTOMER_360."""
    sql = f"""
        SELECT
            customer_token, persona_name, age_band, income_band, family_status,
            state, account_type, rfm_total_score, total_spend, total_transactions,
            top_category_1, top_category_2, top_category_3
        FROM MARTS.CUSTOMER_360
        WHERE customer_token = '{customer_token}'
    """
    df = query_snowflake(sql)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"Customer {customer_token} not found")

    row = df.iloc[0]
    return CustomerProfile(
        customer_token=row["customer_token"],
        persona_name=row["persona_name"],
        age_band=row["age_band"],
        income_band=row["income_band"],
        family_status=row["family_status"],
        state=row["state"],
        account_type=row["account_type"],
        rfm_total_score=int(row["rfm_total_score"]),
        total_spend=float(row["total_spend"]),
        total_transactions=int(row["total_transactions"]),
        top_category_1=row["top_category_1"],
        top_category_2=row["top_category_2"] if pd.notna(row["top_category_2"]) else None,
        top_category_3=row["top_category_3"] if pd.notna(row["top_category_3"]) else None,
    )


@app.get("/customers/random", tags=["customer"], summary="Pick a random customer (for demo)")
def random_customer(persona: Optional[str] = Query(None, description="Optionally filter by persona name")):
    """
    Returns a random customer_token. Useful for demos so you don't have to look up tokens.
    Pass `?persona=Luxury Seeker Vanessa` to get a token for that persona specifically.
    """
    meta = _customer_meta_cache()
    if persona:
        filtered = meta[meta["persona_name"] == persona]
        if filtered.empty:
            available = sorted(meta["persona_name"].unique())
            raise HTTPException(
                status_code=404,
                detail=f"No customers with persona '{persona}'. Available: {available}",
            )
        sample = filtered.sample(1).iloc[0]
    else:
        sample = meta.sample(1).iloc[0]

    return {
        "customer_token": sample["customer_token"],
        "persona_name": sample["persona_name"],
        "cluster": int(sample["cluster"]),
    }


@app.get(
    "/stats/clusters",
    response_model=List[ClusterSummary],
    tags=["analytics"],
    summary="Cluster distribution summary",
)
def cluster_stats():
    """Returns one row per KMeans cluster with size and signature persona."""
    from pathlib import Path
    profiles_path = Path(__file__).resolve().parent.parent / "ml" / "artifacts" / "cluster_profiles.parquet"
    if not profiles_path.exists():
        raise HTTPException(
            status_code=503,
            detail="Cluster profiles not yet generated. Run `python -m ml.segmentation`.",
        )
    df = pd.read_parquet(profiles_path)
    return [
        ClusterSummary(
            cluster=int(r["cluster"]),
            size=int(r["size"]),
            size_pct=float(r["size_pct"]),
            signature_persona=str(r["signature_persona"]),
            signature_lift=float(r["signature_lift"]),
        )
        for _, r in df.iterrows()
    ]
