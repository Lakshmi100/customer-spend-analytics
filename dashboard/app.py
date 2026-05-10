"""
Streamlit dashboard for the ABC Bank Coupon Recommender.

Calls the FastAPI service at localhost:8000 (configurable via env var).

Run:
    # Terminal 1: FastAPI
    uvicorn api.main:app --reload --port 8000

    # Terminal 2: Streamlit
    streamlit run dashboard/app.py

Then open: http://localhost:8501
"""

import os
import time

import pandas as pd
import requests
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://localhost:8000")

# ============================================================================
# Page config
# ============================================================================

st.set_page_config(
    page_title="ABC Bank — Coupon Engine",
    page_icon="🎟",
    layout="wide",
)

# Light styling tweaks
st.markdown("""
<style>
.coupon-card {
    background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
    border-left: 4px solid #2563eb;
    padding: 1.2rem 1.5rem;
    border-radius: 8px;
    margin-bottom: 0.8rem;
}
.coupon-card.tier-luxury     { border-left-color: #a855f7; }
.coupon-card.tier-premium    { border-left-color: #ec4899; }
.coupon-card.tier-mainstream { border-left-color: #2563eb; }
.coupon-card.tier-value      { border-left-color: #16a34a; }
.score-pill {
    display: inline-block;
    background: #1e293b;
    color: #fbbf24;
    padding: 0.2rem 0.6rem;
    border-radius: 999px;
    font-weight: 600;
    font-size: 0.85rem;
    font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Fira Code', monospace;
}
.merchant-name { font-size: 1.25rem; font-weight: 700; color: #0f172a; }
.coupon-title  { color: #475569; margin: 0.4rem 0; }
.reason-text   { color: #64748b; font-size: 0.85rem; font-style: italic; }
.tier-badge {
    display: inline-block;
    padding: 0.15rem 0.6rem;
    border-radius: 4px;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.tier-luxury     { background: #f3e8ff; color: #7e22ce; }
.tier-premium    { background: #fce7f3; color: #be185d; }
.tier-mainstream { background: #dbeafe; color: #1d4ed8; }
.tier-value      { background: #dcfce7; color: #15803d; }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# API helpers
# ============================================================================

@st.cache_data(ttl=60)
def api_get(path: str, params: dict = None):
    """Wrapper around requests.get with error handling."""
    try:
        r = requests.get(f"{API_BASE}{path}", params=params, timeout=10)
        r.raise_for_status()
        return r.json(), None
    except requests.RequestException as e:
        return None, str(e)


@st.cache_data(ttl=300)
def get_personas():
    """Hardcoded persona list — matches our 20 personas."""
    return [
        "Luxury Seeker Vanessa", "Tech Bro Tyler", "DINK Sam",
        "Mid-Career Manager Dev", "Climbing Career Aisha",
        "Empty Nesters Bob & Susan", "Pre-Retiree James",
        "Newlyweds Priya & Raj", "Snowbird Couple Ron & Pat",
        "Soccer Mom Linda", "Stay-at-Home Parent Jenna",
        "Side Hustler Jordan", "New Parent Maya",
        "Healthcare Worker Maria", "Entry-Level Alex",
        "Fitness Enthusiast Kai", "Single Dad Marcus",
        "College Student Sasha", "Frugal Saver Eleanor",
        "Active Retiree Carol",
    ]


# ============================================================================
# Session state
# ============================================================================

if "customer_token" not in st.session_state:
    st.session_state["customer_token"] = None


# ============================================================================
# Sidebar — health + customer picker
# ============================================================================

with st.sidebar:
    st.markdown("### 🏦 ABC Bank")
    st.caption("Coupon Recommendation Engine")

    # Health check
    health, err = api_get("/health")
    if err:
        st.error(f"❌ API unreachable\n\n{err}\n\nIs `uvicorn` running?")
        st.stop()

    if health.get("status") == "ok":
        st.success(f"✓ API connected\n\n{health['customer_360_rows']:,} customers in CUSTOMER_360")
    else:
        st.warning(f"⚠ API degraded — {health.get('error', 'unknown')}")

    st.divider()

    # Customer picker
    st.markdown("### 👤 Pick a customer")

    pick_mode = st.radio(
        "Method",
        ["By persona", "Pick fully random", "Enter token manually"],
        label_visibility="collapsed",
    )

    if pick_mode == "By persona":
        persona = st.selectbox("Persona", get_personas(), index=0)
        if st.button("🎲 Pick random customer", use_container_width=True):
            data, err = api_get("/customers/random", params={"persona": persona})
            if data:
                st.session_state["customer_token"] = data["customer_token"]
                # Bust the cache so the next /coupons call goes through
                api_get.clear()

    elif pick_mode == "Pick fully random":
        if st.button("🎲 Random across all customers", use_container_width=True):
            data, err = api_get("/customers/random")
            if data:
                st.session_state["customer_token"] = data["customer_token"]
                api_get.clear()

    else:
        manual_token = st.text_input("customer_token", value=st.session_state.get("customer_token") or "")
        if manual_token:
            st.session_state["customer_token"] = manual_token

    st.divider()
    st.caption("Built with PySpark · Snowflake · dbt · KMeans · FastAPI · Streamlit")


# ============================================================================
# Main content
# ============================================================================

st.markdown("# 🎟 Personalized Coupon Recommendations")
st.markdown(
    "_Powered by KMeans segmentation + category affinity scoring on a "
    "dbt-built customer 360 mart in Snowflake._"
)

token = st.session_state.get("customer_token")

if not token:
    st.info("👈 Pick a customer in the sidebar to see their coupon recommendations.")
    st.markdown("### How it works")
    st.markdown(
        """
        1. **Synthetic data** — 1,000 ABC Bank customers across 20 persona archetypes,
           with 1.6M transactions over 24 months
        2. **PySpark ingestion** — partitioned parquet, PII tokenized, k-anonymized
           demographics
        3. **Snowflake + dbt** — RAW → STAGING → MARTS layers, 49 data tests passing
        4. **KMeans segmentation** — recovered persona structure with 95-100% purity
           across 18 of 20 personas
        5. **Recommender** — log-scaled affinity (50%) + exponential recency decay (30%) +
           cluster preference signal (20%), filtered by minimum-affinity threshold
        """
    )
    st.stop()


# Two-column layout: customer profile (left) + coupons (right)
left, right = st.columns([1, 1.4])

# ----- Customer profile (left) -----
with left:
    st.markdown("### Customer profile")

    profile, err = api_get(f"/customers/{token}/profile")
    if err:
        st.error(f"Failed to load profile: {err}")
        st.stop()

    st.markdown(
        f"""
        **{profile['persona_name']}**
        Token: `{profile['customer_token']}`
        """
    )

    # Demographics in 2-col grid
    c1, c2 = st.columns(2)
    c1.metric("Age", profile["age_band"])
    c2.metric("Income", profile["income_band"])
    c1.metric("Family", profile["family_status"])
    c2.metric("State", profile["state"])

    st.markdown("---")

    # RFM + spend stats
    c1, c2 = st.columns(2)
    c1.metric("RFM score", f"{profile['rfm_total_score']} / 15")
    c2.metric("Account", profile["account_type"].title())
    c1.metric("Total spend", f"${profile['total_spend']:,.0f}")
    c2.metric("Transactions", f"{profile['total_transactions']:,}")

    st.markdown("---")
    st.markdown("**Top spending categories**")
    for i, cat in enumerate([profile["top_category_1"], profile["top_category_2"], profile["top_category_3"]], 1):
        if cat:
            st.markdown(f"{i}. `{cat}`")


# ----- Recommendations (right) -----
with right:
    st.markdown("### Recommended coupons")

    top_n = st.slider("Number of recommendations", 1, 6, 3, key="topn")

    coupons_data, err = api_get(f"/coupons/{token}", params={"top_n": top_n})
    if err:
        st.error(f"Failed to fetch coupons: {err}")
        st.stop()

    cluster = coupons_data["customer_cluster"]
    persona = coupons_data["customer_persona"]
    st.caption(f"{persona} · Cluster {cluster}")

    for rec in coupons_data["recommendations"]:
        tier_class = f"tier-{rec['tier']}"
        st.markdown(
            f"""
            <div class="coupon-card {tier_class}">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div class="merchant-name">{rec['merchant_name']}
                        <span class="tier-badge {tier_class}" style="margin-left:0.6rem;">
                            {rec['tier']}
                        </span>
                    </div>
                    <div class="score-pill">{rec['score']:.3f}</div>
                </div>
                <div class="coupon-title"><b>{rec['discount_display']}</b> — {rec['title']}</div>
                <div class="reason-text">→ {rec['reasoning']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Score breakdown chart
    st.markdown("---")
    st.markdown("### 📊 Score breakdown")
    st.caption("Each recommendation's score is a weighted blend of three signals.")

    breakdown_rows = []
    for rec in coupons_data["recommendations"]:
        breakdown_rows.append({
            "merchant": rec["merchant_name"],
            "Affinity (50%)": rec["components"]["affinity_score"],
            "Recency (30%)": rec["components"]["recency_score"],
            "Cluster (20%)": rec["components"]["cluster_score"],
        })

    breakdown_df = pd.DataFrame(breakdown_rows).set_index("merchant")
    st.bar_chart(breakdown_df, height=280)

    # Raw signals expander
    with st.expander("🔬 Raw signal values (for debugging)"):
        signals_rows = []
        for rec in coupons_data["recommendations"]:
            signals_rows.append({
                "merchant": rec["merchant_name"],
                "category": rec["category"],
                "affinity_index": f"{rec['signals']['affinity_index']:.2f}x",
                "days_since_last_txn": rec["signals"]["days_since_last_txn"],
                "wallet_share": f"{rec['signals']['wallet_share']*100:.1f}%",
                "score": f"{rec['score']:.4f}",
            })
        st.dataframe(pd.DataFrame(signals_rows), use_container_width=True, hide_index=True)
