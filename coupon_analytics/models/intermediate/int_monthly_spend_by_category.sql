{{
  config(
    materialized = 'view'
  )
}}

/*
    Intermediate: monthly spend aggregated by customer x category.

    This produces one row per (customer, year_month, category) — the natural
    grain for analyzing spend trends over time. Used downstream for:
    - Detecting category preferences
    - Computing month-over-month changes (seasonality, churn signals)
    - Building category affinity features for the ML ranker

    Grain: customer_token + year_month + category (one row each)
*/

WITH base AS (
    SELECT *
    FROM {{ ref('int_customer_transactions') }}
),

aggregated AS (
    SELECT
        customer_token,
        persona_id,
        year_month,
        transaction_year,
        transaction_month,
        category,

        -- Volume metrics
        COUNT(*)                                    AS transaction_count,
        COUNT(DISTINCT transaction_date)            AS active_days,

        -- Spend metrics
        SUM(amount)                                 AS total_spend,
        AVG(amount)                                 AS avg_transaction_amount,
        MIN(amount)                                 AS min_transaction_amount,
        MAX(amount)                                 AS max_transaction_amount,

        -- Channel mix
        SUM(CASE WHEN channel = 'online' THEN amount ELSE 0 END)    AS online_spend,
        SUM(CASE WHEN channel = 'in_store' THEN amount ELSE 0 END)  AS in_store_spend,

        -- Behavioral flags
        SUM(CASE WHEN is_weekend THEN amount ELSE 0 END)            AS weekend_spend,
        SUM(CASE WHEN is_recurring THEN amount ELSE 0 END)          AS recurring_spend,

        -- Time signal
        MIN(transaction_date)                       AS first_txn_date_in_month,
        MAX(transaction_date)                       AS last_txn_date_in_month

    FROM base
    GROUP BY 1, 2, 3, 4, 5, 6
)

SELECT * FROM aggregated
