{{
  config(
    materialized = 'view'
  )
}}

/*
    Intermediate: RFM (Recency, Frequency, Monetary) features per customer.

    RFM is the textbook customer segmentation framework:
        - Recency:   How recently did they transact?  (lower = better)
        - Frequency: How often do they transact?      (higher = better)
        - Monetary:  How much do they spend?          (higher = better)

    Plus quintile rankings (1-5) for each, which we'll use directly in the
    KMeans clustering and as features for the coupon ranker.

    Grain: one row per customer_token
*/

WITH base AS (
    SELECT *
    FROM {{ ref('int_customer_transactions') }}
),

-- Find the most recent transaction date in the dataset (our "today")
reference_date AS (
    SELECT MAX(transaction_date) AS as_of_date
    FROM base
),

customer_rfm AS (
    SELECT
        b.customer_token,
        b.persona_id,
        b.persona_name,
        b.age_band,
        b.income_band,
        b.family_status,

        -- Recency: days since last transaction (lower is better)
        DATEDIFF('day', MAX(b.transaction_date), r.as_of_date) AS recency_days,

        -- Frequency: total number of transactions (over the full history)
        COUNT(*)                                                 AS frequency_total,

        -- Frequency: transactions per active month
        COUNT(*) / NULLIF(COUNT(DISTINCT b.year_month), 0)       AS frequency_per_month,

        -- Monetary: total spend
        SUM(b.amount)                                            AS monetary_total,

        -- Monetary: average transaction amount
        AVG(b.amount)                                            AS monetary_avg_txn,

        -- Monetary: spend per active month
        SUM(b.amount) / NULLIF(COUNT(DISTINCT b.year_month), 0)  AS monetary_per_month,

        -- Activity span
        MIN(b.transaction_date)                                  AS first_transaction_date,
        MAX(b.transaction_date)                                  AS last_transaction_date,
        COUNT(DISTINCT b.year_month)                             AS active_months,
        COUNT(DISTINCT b.transaction_date)                       AS active_days

    FROM base b
    CROSS JOIN reference_date r
    GROUP BY 1, 2, 3, 4, 5, 6, r.as_of_date
),

-- Compute quintile rankings (1 = lowest, 5 = highest) for each metric.
-- For recency, we INVERT so 5 = most recent (best), matching the convention.
rfm_scored AS (
    SELECT
        *,
        -- Recency score: 5 = most recent (lowest days)
        6 - NTILE(5) OVER (ORDER BY recency_days ASC)        AS r_score,
        -- Frequency score: 5 = most frequent
        NTILE(5) OVER (ORDER BY frequency_total ASC)         AS f_score,
        -- Monetary score: 5 = highest spend
        NTILE(5) OVER (ORDER BY monetary_total ASC)          AS m_score
    FROM customer_rfm
),

final AS (
    SELECT
        *,
        -- Composite RFM score (a common 3-digit string like "555" or "143")
        CONCAT(r_score, f_score, m_score) AS rfm_segment_code,

        -- Combined score 3-15
        (r_score + f_score + m_score) AS rfm_total_score
    FROM rfm_scored
)

SELECT * FROM final
