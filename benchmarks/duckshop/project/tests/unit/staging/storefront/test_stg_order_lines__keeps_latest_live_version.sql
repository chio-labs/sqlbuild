TEST (name "stg_order_lines__keeps_latest_live_version");

WITH __source__storefront__order_lines AS (
  SELECT
    'K1' AS order_line_id,
    NULL AS order_id,
    NULL AS line_no,
    NULL AS sku,
    NULL AS quantity,
    NULL AS unit_amount_minor,
    NULL AS tax_amount_minor,
    NULL AS discounts,
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

__expected__stg_order_lines AS (
  SELECT
    'K1' AS order_line_id,
    2 AS source_seq
)
