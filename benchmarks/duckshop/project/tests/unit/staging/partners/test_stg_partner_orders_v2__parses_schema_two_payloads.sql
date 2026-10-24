TEST (name "stg_partner_orders_v2__parses_schema_two_payloads");

WITH __ref__stg_partner_orders AS (
  SELECT
    'MS2' AS message_id,
    'MKT' AS partner_code,
    2 AS schema_version,
    NULL AS received_at,
    'B7' AS external_order_id,
    OBJECT_CONSTRUCT(
      'customer',
      OBJECT_CONSTRUCT('email_hash', 'ABC123'),
      'order',
      OBJECT_CONSTRUCT(
        'currency',
        'usd',
        'totals',
        OBJECT_CONSTRUCT('gross_minor', 4999),
        'placed_at_ms',
        1773137400000
      ),
      'items',
      ARRAY_CONSTRUCT(
        OBJECT_CONSTRUCT('seller_sku', 'A'),
        OBJECT_CONSTRUCT('seller_sku', 'B')
      )
    )::OBJECT AS payload
  UNION ALL
  SELECT
    'MS1',
    'MKT',
    1,
    NULL,
    'A1',
    PARSE_JSON('{}')::OBJECT
  UNION ALL
  SELECT
    'MS4',
    'MKT',
    2,
    NULL,
    'B8',
    PARSE_JSON('{"order": {"currency": "eur"}}')::OBJECT
),

__expected__stg_partner_orders_v2 AS (
  SELECT
    'MKT:B7' AS partner_order_key,
    'abc123' AS buyer_email_hash,
    'USD' AS currency_code,
    4999::DECIMAL(38, 0) AS order_total_minor,
    '2026-03-10 10:10:00'::TIMESTAMP_NTZ AS placed_at_utc
  UNION ALL
  SELECT
    'MKT:B8' AS partner_order_key,
    CAST(NULL AS VARCHAR) AS buyer_email_hash,
    'EUR' AS currency_code,
    CAST(NULL AS DECIMAL(38, 0)) AS order_total_minor,
    CAST(NULL AS TIMESTAMP_NTZ) AS placed_at_utc
),

__assert__missing_items_become_empty_arrays AS (
  SELECT o.partner_order_key
  FROM __ref("stg_partner_orders_v2") AS o
  WHERE ARRAY_SIZE(o.items) <> IFF(o.partner_order_key = 'MKT:B7', 2, 0)
)
