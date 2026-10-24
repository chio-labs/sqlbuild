TEST (name "stg_order_line_discounts__explodes_discounts_and_defaults_kind");

WITH __ref__stg_order_lines AS (
  SELECT
    'L1' AS order_line_id,
    'O1' AS order_id,
    NULL AS line_no,
    NULL AS sku,
    NULL AS quantity,
    NULL AS unit_amount_minor,
    NULL AS gross_amount_minor,
    NULL AS tax_amount_minor,
    NULL AS discount_count,
    ARRAY_CONSTRUCT(
      OBJECT_CONSTRUCT(
        'code',
        'spring10',
        'kind',
        'Promo',
        'amount_minor',
        '150'
      ),
      OBJECT_CONSTRUCT_KEEP_NULL('code', NULL, 'amount_minor', 50)
    )::ARRAY AS discounts,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'L2',
    'O1',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__expected__stg_order_line_discounts AS (
  SELECT
    'L1#0' AS order_line_discount_key,
    'SPRING10' AS discount_code,
    'promo' AS discount_kind,
    150 AS discount_amount_minor
  UNION ALL
  SELECT
    'L1#1' AS order_line_discount_key,
    CAST(NULL AS VARCHAR) AS discount_code,
    'manual' AS discount_kind,
    50 AS discount_amount_minor
)
