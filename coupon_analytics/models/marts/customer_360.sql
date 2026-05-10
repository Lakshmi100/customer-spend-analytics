{{
  config(
    materialized = 'table',
    cluster_by = ['persona_id']
  )
}}

/*
    MART: customer_360
    -------------------------------------------------------------------------
    The central analytics table. One row per active customer with 35+
    features designed for direct consumption by ML models (KMeans clustering,
    coupon recommendation ranker) and BI dashboards.

    Feature groups:
      1. Identifiers + demographics
      2. RFM features (Recency, Frequency, Monetary)
      3. Spend profile (totals, averages, channel mix)
      4. Category preferences (top categories + concentration)
      5. Behavioral signals (weekend %, recurring %, online %)
      6. Recency signals (days since last txn in key categories)
      7. Tenure + lifecycle

    Grain: one row per customer_token (active customers only)
    Materialized as a TABLE for fast ML training queries.
*/

WITH base AS (
    SELECT * FROM {{ ref('int_customer_transactions') }}
),

rfm AS (
    SELECT * FROM {{ ref('int_rfm_features') }}
),

reference_date AS (
    SELECT MAX(transaction_date) AS as_of_date
    FROM base
),

-- Customer-level spend aggregates
customer_spend AS (
    SELECT
        customer_token,

        -- Totals
        COUNT(*)                                                AS total_transactions,
        SUM(amount)                                             AS total_spend,
        AVG(amount)                                             AS avg_transaction_amount,
        MAX(amount)                                             AS max_transaction_amount,
        STDDEV(amount)                                          AS stddev_transaction_amount,

        -- Distinct values (variety signals)
        COUNT(DISTINCT category)                                AS distinct_categories,
        COUNT(DISTINCT merchant_id)                             AS distinct_merchants,
        COUNT(DISTINCT year_month)                              AS active_months,
        COUNT(DISTINCT transaction_date)                        AS active_days,

        -- Channel mix
        SUM(CASE WHEN channel = 'online' THEN amount ELSE 0 END)
            / NULLIF(SUM(amount), 0)                            AS online_spend_share,
        SUM(CASE WHEN channel = 'in_store' THEN amount ELSE 0 END)
            / NULLIF(SUM(amount), 0)                            AS in_store_spend_share,

        -- Behavioral mix
        SUM(CASE WHEN is_weekend THEN amount ELSE 0 END)
            / NULLIF(SUM(amount), 0)                            AS weekend_spend_share,
        SUM(CASE WHEN is_recurring THEN amount ELSE 0 END)
            / NULLIF(SUM(amount), 0)                            AS recurring_spend_share,

        -- Geographic stickiness
        SUM(CASE WHEN is_home_state_txn THEN amount ELSE 0 END)
            / NULLIF(SUM(amount), 0)                            AS home_state_spend_share,

        -- Payment mix
        SUM(CASE WHEN payment_method = 'credit' THEN amount ELSE 0 END)
            / NULLIF(SUM(amount), 0)                            AS credit_spend_share

    FROM base
    GROUP BY 1
),

-- Per-customer category share (which categories dominate spending)
category_spend AS (
    SELECT
        customer_token,
        category,
        SUM(amount) AS category_total
    FROM base
    GROUP BY 1, 2
),

category_with_rank AS (
    SELECT
        customer_token,
        category,
        category_total,
        ROW_NUMBER() OVER (
            PARTITION BY customer_token ORDER BY category_total DESC
        ) AS category_rank,
        category_total / SUM(category_total) OVER (PARTITION BY customer_token)
            AS category_share
    FROM category_spend
),

top_categories AS (
    SELECT
        customer_token,
        MAX(CASE WHEN category_rank = 1 THEN category END)         AS top_category_1,
        MAX(CASE WHEN category_rank = 1 THEN category_share END)   AS top_category_1_share,
        MAX(CASE WHEN category_rank = 2 THEN category END)         AS top_category_2,
        MAX(CASE WHEN category_rank = 2 THEN category_share END)   AS top_category_2_share,
        MAX(CASE WHEN category_rank = 3 THEN category END)         AS top_category_3,
        MAX(CASE WHEN category_rank = 3 THEN category_share END)   AS top_category_3_share
    FROM category_with_rank
    GROUP BY 1
),

-- Recency in key high-value categories (used as ML features for coupon ranker)
category_recency AS (
    SELECT
        b.customer_token,
        DATEDIFF('day',
            MAX(CASE WHEN b.category = 'travel_air' THEN b.transaction_date END),
            r.as_of_date) AS days_since_travel_air,
        DATEDIFF('day',
            MAX(CASE WHEN b.category = 'dining' THEN b.transaction_date END),
            r.as_of_date) AS days_since_dining,
        DATEDIFF('day',
            MAX(CASE WHEN b.category = 'luxury_goods' THEN b.transaction_date END),
            r.as_of_date) AS days_since_luxury,
        DATEDIFF('day',
            MAX(CASE WHEN b.category = 'fitness_gym' THEN b.transaction_date END),
            r.as_of_date) AS days_since_fitness,
        DATEDIFF('day',
            MAX(CASE WHEN b.category = 'kids_baby' THEN b.transaction_date END),
            r.as_of_date) AS days_since_kids_baby
    FROM base b
    CROSS JOIN reference_date r
    GROUP BY 1, r.as_of_date
),

-- Final assembly
final AS (
    SELECT
        -- ===== IDENTIFIERS =====
        c.customer_token,
        c.persona_id,
        c.persona_name,

        -- ===== DEMOGRAPHICS =====
        c.age_band,
        c.income_band,
        c.household_income_band,
        c.family_status,
        c.num_dependents,
        c.geography_type,
        c.state,
        c.zip_prefix,
        c.account_type,
        c.credit_score_band,

        -- ===== TENURE =====
        c.account_open_date,
        DATEDIFF('day', c.account_open_date, r.as_of_date) AS account_tenure_days,

        -- ===== RFM FEATURES =====
        rfm.recency_days,
        rfm.frequency_total,
        rfm.frequency_per_month,
        rfm.monetary_total,
        rfm.monetary_avg_txn,
        rfm.monetary_per_month,
        rfm.r_score,
        rfm.f_score,
        rfm.m_score,
        rfm.rfm_segment_code,
        rfm.rfm_total_score,

        -- ===== SPEND PROFILE =====
        cs.total_transactions,
        cs.total_spend,
        cs.avg_transaction_amount,
        cs.max_transaction_amount,
        cs.stddev_transaction_amount,
        cs.distinct_categories,
        cs.distinct_merchants,
        cs.active_months,
        cs.active_days,

        -- ===== CHANNEL & BEHAVIOR =====
        cs.online_spend_share,
        cs.in_store_spend_share,
        cs.weekend_spend_share,
        cs.recurring_spend_share,
        cs.home_state_spend_share,
        cs.credit_spend_share,

        -- ===== TOP CATEGORIES =====
        tc.top_category_1,
        tc.top_category_1_share,
        tc.top_category_2,
        tc.top_category_2_share,
        tc.top_category_3,
        tc.top_category_3_share,

        -- ===== CATEGORY RECENCY (coupon-ranker features) =====
        cr.days_since_travel_air,
        cr.days_since_dining,
        cr.days_since_luxury,
        cr.days_since_fitness,
        cr.days_since_kids_baby,

        -- ===== METADATA =====
        r.as_of_date,
        CURRENT_TIMESTAMP() AS dbt_built_at

    FROM (SELECT DISTINCT
              customer_token, persona_id, persona_name,
              age_band, income_band, household_income_band,
              family_status, num_dependents, geography_type,
              customer_state AS state, zip_prefix, account_type,
              credit_score_band, account_open_date
          FROM base) c
    LEFT JOIN rfm USING (customer_token)
    LEFT JOIN customer_spend cs USING (customer_token)
    LEFT JOIN top_categories tc USING (customer_token)
    LEFT JOIN category_recency cr USING (customer_token)
    CROSS JOIN reference_date r
)

SELECT * FROM final
