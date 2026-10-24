TEST (name "stg_web_cart_events__explodes_cart_items_with_signed_quantities");

WITH __ref__stg_web_events AS (
  SELECT
    'e1' AS event_id,
    NULL AS received_at,
    'add_to_cart' AS event_type,
    '2026-03-10 10:00:00'::TIMESTAMP_NTZ AS event_at_utc,
    'v1' AS anonymous_id,
    NULL AS customer_id,
    NULL AS user_email,
    NULL AS page_url,
    NULL AS page_path,
    NULL AS referrer_host,
    NULL AS user_agent,
    NULL AS locale,
    NULL AS client_timezone,
    FALSE AS is_bot,
    PARSE_JSON('{"currency": "eur"}')::OBJECT AS properties,
    ARRAY_CONSTRUCT(
      OBJECT_CONSTRUCT(
        'sku',
        'duck_1',
        'quantity',
        2,
        'price_minor',
        500
      ),
      OBJECT_CONSTRUCT('sku', ' duck 2 ', 'price_minor', 900)
    )::ARRAY AS items
  UNION ALL
  SELECT
    'e2',
    NULL,
    'remove_from_cart',
    '2026-03-10 10:05:00'::TIMESTAMP_NTZ,
    'v1',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
    PARSE_JSON('{}')::OBJECT,
    PARSE_JSON('[{"sku": "DUCK-1"}]')::ARRAY
  UNION ALL
  SELECT
    'e3',
    NULL,
    'page_view',
    '2026-03-10 10:06:00'::TIMESTAMP_NTZ,
    'v1',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
    PARSE_JSON('{}')::OBJECT,
    PARSE_JSON('[{"sku": "DUCK-9"}]')::ARRAY
),

__expected__stg_web_cart_events AS (
  SELECT
    'e1:0' AS cart_event_key,
    'add' AS action,
    'DUCK-1' AS sku,
    2 AS quantity_delta,
    500 AS unit_amount_minor,
    'EUR' AS currency_code
  UNION ALL
  SELECT
    'e1:1' AS cart_event_key,
    'add' AS action,
    'DUCK2' AS sku,
    1 AS quantity_delta,
    900 AS unit_amount_minor,
    'EUR' AS currency_code
  UNION ALL
  SELECT
    'e2:0' AS cart_event_key,
    'remove' AS action,
    'DUCK-1' AS sku,
    -1 AS quantity_delta,
    CAST(NULL AS INT) AS unit_amount_minor,
    CAST(NULL AS VARCHAR) AS currency_code
)
