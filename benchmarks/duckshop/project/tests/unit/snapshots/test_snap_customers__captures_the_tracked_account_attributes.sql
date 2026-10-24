TEST (name "snap_customers__captures_the_tracked_account_attributes");

WITH __ref__stg_customers AS (
  SELECT
    'C1' AS customer_id,
    'wren@example.com' AS email_normalised,
    NULL AS phone_normalised,
    NULL AS first_name,
    NULL AS last_name,
    'EU' AS region_code,
    'eu-web' AS storefront_code,
    NULL AS created_at,
    'de' AS preferred_language,
    TRUE AS marketing_opt_in,
    NULL AS consent_types,
    NULL AS birth_year,
    NULL AS preferences,
    NULL AS source_seq,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ AS source_loaded_at
  UNION ALL
  SELECT
    'C2',
    'bob@example.com',
    NULL,
    NULL,
    NULL,
    'US',
    'us-web',
    NULL,
    NULL,
    FALSE,
    NULL,
    NULL,
    NULL,
    NULL,
    '2026-03-02 10:00:00'::TIMESTAMP_NTZ
),

__expected__snap_customers AS (
  SELECT
    'C1' AS customer_id,
    'wren@example.com' AS email_normalised,
    'EU' AS region_code,
    TRUE AS marketing_opt_in,
    '2026-03-01 10:00:00'::TIMESTAMPNTZ AS source_loaded_at
  UNION ALL
  SELECT
    'C2' AS customer_id,
    'bob@example.com' AS email_normalised,
    'US' AS region_code,
    FALSE AS marketing_opt_in,
    '2026-03-02 10:00:00'::TIMESTAMPNTZ AS source_loaded_at
),

__assert__customer_id_is_unique_and_present AS (
  SELECT t.customer_id
  FROM __ref("snap_customers") AS t
  GROUP BY
    t.customer_id
  HAVING
    COUNT(*) > 1
    OR t.customer_id IS NULL
)
