TEST (name "stg_customer_addresses__keeps_latest_live_version");

WITH __source__storefront__customer_addresses AS (
  SELECT
    'K1' AS address_id,
    NULL AS customer_id,
    NULL AS line1,
    NULL AS line2,
    NULL AS city,
    NULL AS postcode,
    NULL AS country_code,
    NULL AS is_default,
    NULL AS valid_from,
    NULL AS geo,
    'I' AS _op,
    1 AS _seq,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'K1',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'U',
    2,
    '2026-01-02 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'K2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'I',
    3,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'K2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'D',
    4,
    '2026-01-03 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_customer_addresses AS (
  SELECT
    'K1' AS address_id,
    2 AS source_seq
)
