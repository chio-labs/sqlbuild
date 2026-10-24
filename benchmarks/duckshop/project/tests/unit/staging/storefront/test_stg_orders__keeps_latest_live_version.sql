TEST (name "stg_orders__keeps_latest_live_version");

WITH __source__storefront__orders AS (
  SELECT
    'K1' AS order_id,
    NULL AS customer_id,
    NULL AS storefront_code,
    NULL AS currency_code,
    NULL AS placed_at,
    NULL AS status,
    NULL AS shipping_address_id,
    NULL AS attributes,
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
    'D',
    4,
    '2026-01-03 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_orders AS (
  SELECT
    'K1' AS order_id,
    2 AS source_seq
)
