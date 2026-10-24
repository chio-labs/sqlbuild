TEST (name "stg_web_checkout_steps__keeps_first_arrival_at_each_step");

WITH __ref__stg_web_events AS (
  SELECT
    'c1' AS event_id,
    NULL AS received_at,
    'checkout_started' AS event_type,
    '2026-03-10 10:00:00'::TIMESTAMP_NTZ AS event_at_utc,
    'v1' AS anonymous_id,
    NULL AS customer_id,
    NULL AS user_email,
    'https://shop.example.com/checkout/step-1' AS page_url,
    '/checkout/step-1' AS page_path,
    NULL AS referrer_host,
    NULL AS user_agent,
    NULL AS locale,
    NULL AS client_timezone,
    FALSE AS is_bot,
    PARSE_JSON('{}')::OBJECT AS properties,
    PARSE_JSON('[]')::ARRAY AS items
  UNION ALL
  SELECT
    'c2',
    NULL,
    'checkout_step',
    '2026-03-10 10:05:00'::TIMESTAMP_NTZ,
    'v1',
    NULL,
    NULL,
    'https://shop.example.com/checkout',
    '/checkout',
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
    PARSE_JSON('{"step": 2, "step_name": "Shipping"}')::OBJECT,
    PARSE_JSON('[]')::ARRAY
  UNION ALL
  SELECT
    'c3',
    NULL,
    'checkout_step',
    '2026-03-10 10:06:00'::TIMESTAMP_NTZ,
    'v1',
    NULL,
    NULL,
    'https://shop.example.com/checkout',
    '/checkout',
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
    PARSE_JSON('{"step": 2, "step_name": "Shipping"}')::OBJECT,
    PARSE_JSON('[]')::ARRAY
  UNION ALL
  SELECT
    'c4',
    NULL,
    'checkout_step',
    '2026-03-10 10:10:00'::TIMESTAMP_NTZ,
    'v1',
    NULL,
    NULL,
    'https://shop.example.com/checkout',
    '/checkout',
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
    PARSE_JSON('{"step": 3, "payment_option": "Card"}')::OBJECT,
    PARSE_JSON('[]')::ARRAY
  UNION ALL
  SELECT
    'c5',
    NULL,
    'checkout_step',
    '2026-03-10 10:11:00'::TIMESTAMP_NTZ,
    'v1',
    NULL,
    NULL,
    'https://shop.example.com/checkout/review',
    '/checkout/review',
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
    PARSE_JSON('{}')::OBJECT,
    PARSE_JSON('[]')::ARRAY
  UNION ALL
  SELECT
    'c6',
    NULL,
    'checkout_step',
    '2026-03-10 10:12:00'::TIMESTAMP_NTZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
    PARSE_JSON('{"step": 1}')::OBJECT,
    PARSE_JSON('[]')::ARRAY
),

__expected__stg_web_checkout_steps AS (
  SELECT
    'v1#1' AS checkout_step_key,
    1 AS step_number,
    CAST(NULL AS VARCHAR) AS step_name,
    '2026-03-10 10:00:00'::TIMESTAMP_NTZ AS first_reached_at_utc,
    CAST(NULL AS VARCHAR) AS payment_option
  UNION ALL
  SELECT
    'v1#2' AS checkout_step_key,
    2 AS step_number,
    'shipping' AS step_name,
    '2026-03-10 10:05:00'::TIMESTAMP_NTZ AS first_reached_at_utc,
    CAST(NULL AS VARCHAR) AS payment_option
  UNION ALL
  SELECT
    'v1#3' AS checkout_step_key,
    3 AS step_number,
    CAST(NULL AS VARCHAR) AS step_name,
    '2026-03-10 10:10:00'::TIMESTAMP_NTZ AS first_reached_at_utc,
    'card' AS payment_option
)
