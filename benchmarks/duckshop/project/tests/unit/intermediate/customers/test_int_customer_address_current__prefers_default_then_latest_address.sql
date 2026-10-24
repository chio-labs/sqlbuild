TEST (name "int_customer_address_current__prefers_default_then_latest_address");

WITH __ref__stg_customer_addresses AS (
  SELECT
    'A1' AS address_id,
    'C1' AS customer_id,
    NULL AS line1,
    NULL AS line2,
    'Berlin' AS city,
    'DE' AS country_code,
    NULL AS postcode_canonical,
    FALSE AS is_default,
    '2025-06-01 00:00:00 +00:00'::TIMESTAMP_TZ AS valid_from,
    NULL AS latitude,
    NULL AS longitude,
    NULL AS geo,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'A2',
    'C1',
    NULL,
    NULL,
    'Munich',
    'DE',
    NULL,
    TRUE,
    '2024-01-01 00:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'A3',
    'C1',
    NULL,
    NULL,
    'Paris',
    'FR',
    NULL,
    FALSE,
    '2026-01-01 00:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'A4',
    'C2',
    NULL,
    NULL,
    'Austin',
    'US',
    NULL,
    FALSE,
    '2025-01-01 00:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__seed__countries AS (
  SELECT
    'DE' AS country_code,
    NULL AS country_name,
    'EU' AS region_code,
    NULL AS default_timezone,
    NULL AS currency_code,
    NULL AS vat_registered
  UNION ALL
  SELECT
    'FR',
    NULL,
    'EU',
    NULL,
    NULL,
    NULL
),

__expected__int_customer_address_current AS (
  SELECT
    'C1' AS customer_id,
    'A2' AS address_id,
    'Munich' AS city,
    'EU' AS region_code,
    TRUE AS is_explicit_default,
    3 AS address_count,
    2 AS distinct_countries
  UNION ALL
  SELECT
    'C2' AS customer_id,
    'A4' AS address_id,
    'Austin' AS city,
    CAST(NULL AS VARCHAR) AS region_code,
    FALSE AS is_explicit_default,
    1 AS address_count,
    1 AS distinct_countries
)
