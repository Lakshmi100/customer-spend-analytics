{{
  config(
    materialized = 'view'
  )
}}

/*
    Staging layer: lightly cleaned customer master.
    - 1:1 with source (no joins, no aggregations)
    - Renames where helpful
    - Filters to active accounts
    - Casts types if needed
*/

WITH source AS (
    SELECT * FROM {{ source('raw', 'customers') }}
),

renamed AS (
    SELECT
        -- Identifiers
        customer_token,
        account_token,
        persona_id,
        persona_name,

        -- Demographics (k-anonymized)
        age_band,
        income_band,
        household_income_band,
        family_status,
        num_dependents,

        -- Geography
        geography      AS geography_type,
        state,
        zip_prefix,

        -- Account attributes
        account_open_date,
        account_type,
        credit_score_band,
        is_active,

        -- Audit fields
        created_at,
        ingested_at,
        batch_id

    FROM source
    --WHERE is_active = TRUE -- Uncomment if you want to filter to active accounts only
)

SELECT * FROM renamed