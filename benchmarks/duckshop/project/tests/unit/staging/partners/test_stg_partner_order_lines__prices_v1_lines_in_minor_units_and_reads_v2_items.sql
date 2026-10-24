TEST (name "stg_partner_order_lines__prices_v1_lines_in_minor_units_and_reads_v2_items");

WITH __ref__stg_partner_orders_v1 AS (
  SELECT
    'MKT:A1' AS partner_order_key,
    NULL AS partner_code,
    NULL AS external_order_id,
    NULL AS buyer_email,
    'EUR' AS currency_code,
    NULL AS order_total,
    NULL AS placed_at,
    ARRAY_CONSTRUCT(
      OBJECT_CONSTRUCT(
        'sku',
        'duck_mal 01',
        'qty',
        2,
        'price',
        '12.345'
      )
    )::ARRAY AS lines
  UNION ALL
  SELECT
    'MKT:A2',
    NULL,
    NULL,
    NULL,
    'KWD',
    NULL,
    NULL,
    ARRAY_CONSTRUCT(
      OBJECT_CONSTRUCT(
        'sku',
        'BATH-EID-1',
        'qty',
        1,
        'price',
        '3.5'
      )
    )::ARRAY
  UNION ALL
  SELECT
    'MKT:A3',
    NULL,
    NULL,
    NULL,
    'XXX',
    NULL,
    NULL,
    ARRAY_CONSTRUCT(
      OBJECT_CONSTRUCT(
        'sku',
        'X',
        'qty',
        1,
        'price',
        '1'
      )
    )::ARRAY
),

__ref__stg_partner_orders_v2 AS (
  SELECT
    'MKT:B7' AS partner_order_key,
    NULL AS partner_code,
    NULL AS external_order_id,
    NULL AS buyer_email_hash,
    'USD' AS currency_code,
    NULL AS order_total_minor,
    NULL AS placed_at_utc,
    ARRAY_CONSTRUCT(
      OBJECT_CONSTRUCT(
        'seller_sku',
        'pond-pump',
        'quantity',
        1,
        'unit_price_minor',
        4999
      )
    )::ARRAY AS items
),

__seed__currencies AS (
  SELECT
    'EUR' AS currency_code,
    NULL AS currency_name,
    2 AS minor_unit_exponent,
    NULL AS symbol
  UNION ALL
  SELECT
    'KWD',
    NULL,
    3,
    NULL
),

__expected__stg_partner_order_lines AS (
  SELECT
    'MKT:A1#0' AS partner_order_line_key,
    1 AS payload_version,
    'DUCK-MAL01' AS sku,
    2 AS quantity,
    1235::DECIMAL(38, 0) AS unit_amount_minor
  UNION ALL
  SELECT
    'MKT:A2#0' AS partner_order_line_key,
    1 AS payload_version,
    'BATH-EID-1' AS sku,
    1 AS quantity,
    3500::DECIMAL(38, 0) AS unit_amount_minor
  UNION ALL
  SELECT
    'MKT:B7#0' AS partner_order_line_key,
    2 AS payload_version,
    'POND-PUMP' AS sku,
    1 AS quantity,
    4999::DECIMAL(38, 0) AS unit_amount_minor
)
