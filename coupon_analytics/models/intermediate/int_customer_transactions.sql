{{
  config(
    materialized = 'view'
  )
}}

/*
    Intermediate: customer + transaction join, filtered to active customers.

    This is the FACT table foundation. Most downstream models start from here
    instead of re-joining customers and transactions every time.

    Why this lives in INTERMEDIATE (not staging):
    - Filtering to is_active = TRUE is a business decision (most use cases want
      active customers, but a churn model might want inactive too).
    - Joining customers + transactions is reusable logic, not a one-off.
*/

WITH active_customers AS (
    SELECT *
    FROM {{ ref('stg_customers') }}
    WHERE is_active = TRUE
),

transactions AS (
    SELECT *
    FROM {{ ref('stg_transactions') }}
),

joined AS (
    SELECT
        -- Transaction core
        t.transaction_id,
        t.transaction_date,
        t.transaction_ts,
        t.amount,
        t.category,
        t.merchant_id,
        t.merchant_name,
        t.channel,
        t.payment_method,
        t.is_recurring,
        t.day_of_week,
        t.is_weekend,
        t.transaction_hour,
        t.year_month,
        t.transaction_year,
        t.transaction_month,

        -- Customer attributes (denormalized for analytical convenience)
        c.customer_token,
        c.persona_id,
        c.persona_name,
        c.age_band,
        c.income_band,
        c.household_income_band,
        c.family_status,
        c.num_dependents,
        c.geography_type,
        c.state              AS customer_state,
        t.state              AS transaction_state,
        c.zip_prefix,
        c.account_open_date,
        c.account_type,
        c.credit_score_band,

        -- Derived: was the transaction in the customer's home state?
        CASE
            WHEN c.state = t.state THEN TRUE
            ELSE FALSE
        END AS is_home_state_txn

    FROM transactions t
    INNER JOIN active_customers c
        ON t.customer_token = c.customer_token
)

SELECT * FROM joined
