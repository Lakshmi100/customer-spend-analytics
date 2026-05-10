{{
  config(
    materialized = 'view'
  )
}}

/*
    Staging layer: cleaned transaction stream.
    - Filters to posted transactions only
    - Adds derived day_of_week and is_weekend flags for downstream features
    - Renames year_month to be SQL-friendly
*/

WITH source AS (
    SELECT * FROM {{ source('raw', 'transactions') }}
),

cleaned AS (
    SELECT
        -- Identifiers
        transaction_id,
        customer_token,
        merchant_id,

        -- Transaction core fields
        transaction_date,
        transaction_ts,
        amount,
        category,
        merchant_name,
        channel,
        payment_method,
        is_recurring,

        -- Derived time features
        DAYOFWEEK(transaction_date) AS day_of_week,
        CASE
            WHEN DAYOFWEEK(transaction_date) IN (0, 6) THEN TRUE
            ELSE FALSE
        END AS is_weekend,
        HOUR(transaction_ts) AS transaction_hour,

        -- Partition / time keys
        TO_CHAR(transaction_date, 'YYYY-MM') AS year_month, 
        transaction_year,
        transaction_month,

        -- Geography
        state,

        -- Status
        txn_status,

        -- Audit
        ingested_at,
        batch_id

    FROM source
    WHERE txn_status = 'posted'
      AND amount > 0
)

SELECT * FROM cleaned