{{
  config(
    materialized = 'table',
    cluster_by = ['customer_token']
  )
}}

/*
    MART: category_affinity
    -------------------------------------------------------------------------
    For each (customer, category) pair: how much they spend, what share of
    their wallet that category represents, and how their share compares to
    the population average. This is the input to the coupon ranker —
    high-affinity categories that the customer is currently active in
    are the best coupon targets.

    Signals:
      - spend_share:        customer's share of wallet in this category
      - population_share:   what % of overall txns are in this category
      - affinity_index:     spend_share / population_share
                            (>1 = customer prefers this category vs avg)
      - is_top_3:           is this in the customer's top-3 categories?

    Grain: one row per (customer_token, category)
*/

WITH base AS (
    SELECT * FROM {{ ref('int_customer_transactions') }}
),

-- Population-level: what % of all spend is in each category?
population_shares AS (
    SELECT
        category,
        SUM(amount) / SUM(SUM(amount)) OVER ()  AS population_share
    FROM base
    GROUP BY 1
),

-- Customer × category aggregates
customer_category AS (
    SELECT
        customer_token,
        persona_id,
        category,
        COUNT(*)            AS transactions,
        SUM(amount)         AS total_spend,
        AVG(amount)         AS avg_transaction,
        MAX(transaction_date) AS last_transaction_date
    FROM base
    GROUP BY 1, 2, 3
),

-- Add wallet share + affinity index
with_shares AS (
    SELECT
        cc.*,
        cc.total_spend / SUM(cc.total_spend) OVER (PARTITION BY cc.customer_token)
            AS spend_share,
        ROW_NUMBER() OVER (
            PARTITION BY cc.customer_token ORDER BY cc.total_spend DESC
        ) AS category_rank
    FROM customer_category cc
),

with_affinity AS (
    SELECT
        ws.*,
        ps.population_share,
        ws.spend_share / NULLIF(ps.population_share, 0) AS affinity_index,
        CASE WHEN ws.category_rank <= 3 THEN TRUE ELSE FALSE END AS is_top_3
    FROM with_shares ws
    LEFT JOIN population_shares ps USING (category)
),

-- Add days_since_last_txn for this category
final AS (
    SELECT
        customer_token,
        persona_id,
        category,
        transactions,
        total_spend,
        avg_transaction,
        spend_share,
        population_share,
        affinity_index,
        category_rank,
        is_top_3,
        last_transaction_date,
        DATEDIFF('day', last_transaction_date,
                 (SELECT MAX(transaction_date) FROM base)) AS days_since_last_txn
    FROM with_affinity
)

SELECT * FROM final
