TEST (name "stg_partner_orders_v1__parses_schema_one_payloads");

WITH __ref__stg_partner_orders AS (
  SELECT
    'MS1' AS message_id,
    'MKT' AS partner_code,
    1 AS schema_version,
    NULL AS received_at,
    'A1' AS external_order_id,
    OBJECT_CONSTRUCT(
      'buyer',
      OBJECT_CONSTRUCT('email', ' Duck.Fan+mkt@Example.com '),
      'total',
      OBJECT_CONSTRUCT(
        'currency',
        'eur',
        'amount',
        '24.69'
      ),
      'created',
      '2026-03-10 09:00:00 +01:00',
      'lines',
      ARRAY_CONSTRUCT(OBJECT_CONSTRUCT('sku', 'DUCK-MAL-01'))
    )::OBJECT AS payload
  UNION ALL
  SELECT
    'MS2',
    'MKT',
    2,
    NULL,
    'B7',
    PARSE_JSON('{}')::OBJECT
  UNION ALL
  SELECT
    'MS3',
    'MKT',
    1,
    NULL,
    'A2',
    OBJECT_CONSTRUCT_KEEP_NULL(
      'buyer',
      OBJECT_CONSTRUCT_KEEP_NULL('email', NULL),
      'total',
      OBJECT_CONSTRUCT(
        'currency',
        'kwd',
        'amount',
        '3.5'
      ),
      'created',
      '2026-03-11 10:00:00 +03:00'
    )::OBJECT
),

__expected__stg_partner_orders_v1 AS (
  SELECT
    'MKT:A1' AS partner_order_key,
    'duck.fan@example.com' AS buyer_email,
    'EUR' AS currency_code,
    24.69::DECIMAL(18, 3) AS order_total,
    '2026-03-10 09:00:00 +01:00'::TIMESTAMP_TZ AS placed_at
  UNION ALL
  SELECT
    'MKT:A2' AS partner_order_key,
    CAST(NULL AS VARCHAR) AS buyer_email,
    'KWD' AS currency_code,
    3.5::DECIMAL(18, 3) AS order_total,
    '2026-03-11 10:00:00 +03:00'::TIMESTAMP_TZ AS placed_at
),

__assert__missing_lines_become_empty_arrays AS (
  SELECT o.partner_order_key
  FROM __ref("stg_partner_orders_v1") AS o
  WHERE ARRAY_SIZE(o.lines) <> IFF(o.partner_order_key = 'MKT:A1', 1, 0)
)
