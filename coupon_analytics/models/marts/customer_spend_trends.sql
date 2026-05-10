{{
  config(
    materialized = 'table',
    cluster_by = ['customer_token', 'year_month']
  )
}}

/*
    MART: customer_spend_trends
    -------------------------------------------------------------------------
    Monthly time-series view of each customer's spending. Includes:
      - Total spend per month
      - Month-over-month change (absolute and %)
      - Trailing 3-month rolling average
      - Spend rank among the customer's own months
      - Activity flag (did they transact this month at all?)

    Used by the ML pipeline for:
      - Trend / momentum features
      - Churn-risk detection (declining MoM)
      - Seasonality patterns

    Grain: one row per (customer_token, year_month)
*/

WITH monthly AS (
    SELECT
        customer_token,
        persona_id,
        year_month,
        transaction_year,
        transaction_month,
        COUNT(*)               AS transactions,
        SUM(amount)            AS total_spend,
        AVG(amount)            AS avg_transaction,
        COUNT(DISTINCT category) AS distinct_categories
    FROM {{ ref('int_customer_transactions') }}
    GROUP BY 1, 2, 3, 4, 5
),

with_lag AS (
    SELECT
        *,
        LAG(total_spend) OVER (
            PARTITION BY customer_token ORDER BY year_month
        ) AS prev_month_spend,

        AVG(total_spend) OVER (
            PARTITION BY customer_token
            ORDER BY year_month
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS rolling_3mo_avg_spend,

        AVG(total_spend) OVER (
            PARTITION BY customer_token
        ) AS lifetime_avg_monthly_spend,

        ROW_NUMBER() OVER (
            PARTITION BY customer_token ORDER BY total_spend DESC
        ) AS month_spend_rank
    FROM monthly
),

final AS (
    SELECT
        customer_token,
        persona_id,
        year_month,
        transaction_year,
        transaction_month,
        transactions,
        total_spend,
        avg_transaction,
        distinct_categories,
        prev_month_spend,
        rolling_3mo_avg_spend,
        lifetime_avg_monthly_spend,
        month_spend_rank,

        -- Month-over-month delta
        total_spend - prev_month_spend                                  AS mom_change_abs,
        (total_spend - prev_month_spend) / NULLIF(prev_month_spend, 0)  AS mom_change_pct,

        -- vs lifetime baseline
        total_spend - lifetime_avg_monthly_spend                        AS vs_lifetime_avg_abs,
        (total_spend - lifetime_avg_monthly_spend)
            / NULLIF(lifetime_avg_monthly_spend, 0)                     AS vs_lifetime_avg_pct,

        -- Flags
        CASE
            WHEN total_spend > rolling_3mo_avg_spend * 1.3 THEN 'spike'
            WHEN total_spend < rolling_3mo_avg_spend * 0.7 THEN 'dip'
            ELSE 'normal'
        END AS spend_regime
    FROM with_lag
)

SELECT * FROM final
ORDER BY customer_token, year_month
