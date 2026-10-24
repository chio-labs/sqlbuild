TEST (name "stg_cart_items__coerces_loosely_typed_cart_payloads");

WITH __ref__stg_carts AS (
  SELECT
    'CT1' AS cart_id,
    NULL AS customer_id,
    NULL AS anonymous_id,
    NULL AS storefront_code,
    NULL AS cart_status,
    NULL AS created_at,
    NULL AS updated_at,
    NULL AS line_count,
    NULL AS coupon_code,
    OBJECT_CONSTRUCT(
      'items',
      ARRAY_CONSTRUCT(
        OBJECT_CONSTRUCT(
          'sku',
          'duck_mal 01',
          'qty',
          2,
          'unit_minor',
          '1299',
          'added_at',
          '2026-03-10 09:00:00 +01:00'
        ),
        OBJECT_CONSTRUCT(
          'sku',
          'BATH-EID-1',
          'qty',
          '3',
          'unit_minor',
          899
        ),
        OBJECT_CONSTRUCT(
          'sku',
          'POND-PUMP',
          'qty',
          'two',
          'added_at',
          'not a date'
        )
      )
    )::OBJECT AS contents,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'CT2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    PARSE_JSON('{}')::OBJECT,
    NULL,
    NULL
),

__expected__stg_cart_items AS (
  SELECT
    'CT1/0' AS cart_item_key,
    'DUCK-MAL01' AS sku,
    2 AS quantity,
    1299 AS unit_amount_minor,
    '2026-03-10 09:00:00 +01:00'::TIMESTAMPTZ AS added_at
  UNION ALL
  SELECT
    'CT1/1' AS cart_item_key,
    'BATH-EID-1' AS sku,
    3 AS quantity,
    899 AS unit_amount_minor,
    CAST(NULL AS TIMESTAMPTZ) AS added_at
  UNION ALL
  SELECT
    'CT1/2' AS cart_item_key,
    'POND-PUMP' AS sku,
    CAST(NULL AS INT) AS quantity,
    CAST(NULL AS INT) AS unit_amount_minor,
    CAST(NULL AS TIMESTAMPTZ) AS added_at
)
