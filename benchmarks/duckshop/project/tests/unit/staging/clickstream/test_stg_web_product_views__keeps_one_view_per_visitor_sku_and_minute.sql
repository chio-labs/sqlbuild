TEST (name "stg_web_product_views__keeps_one_view_per_visitor_sku_and_minute");

WITH __ref__stg_web_events AS (
  SELECT
    'e1' AS event_id,
    NULL AS received_at,
    'product_view' AS event_type,
    '2026-03-10 10:00:10'::TIMESTAMP_NTZ AS event_at_utc,
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
    PARSE_JSON('{"sku": "duck_1", "list": {"name": "Search", "position": 3}}')::OBJECT AS properties,
    PARSE_JSON('[]')::ARRAY AS items
  UNION ALL
  SELECT
    'e2',
    NULL,
    'product_view',
    '2026-03-10 10:00:50'::TIMESTAMP_NTZ,
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
    PARSE_JSON('{"sku": "DUCK-1"}')::OBJECT,
    PARSE_JSON('[]')::ARRAY
  UNION ALL
  SELECT
    'e3',
    NULL,
    'product_view',
    '2026-03-10 10:01:00'::TIMESTAMP_NTZ,
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
    PARSE_JSON('{"sku": "DUCK-1"}')::OBJECT,
    PARSE_JSON('[]')::ARRAY
  UNION ALL
  SELECT
    'e4',
    NULL,
    'product_view',
    '2026-03-10 10:02:00'::TIMESTAMP_NTZ,
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
    PARSE_JSON('[]')::ARRAY
  UNION ALL
  SELECT
    'e5',
    NULL,
    'product_view',
    '2026-03-10 10:03:00'::TIMESTAMP_NTZ,
    'v1',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    TRUE,
    PARSE_JSON('{"sku": "DUCK-1"}')::OBJECT,
    PARSE_JSON('[]')::ARRAY
),

__expected__stg_web_product_views AS (
  SELECT
    'v1|DUCK-1|202603101000' AS product_view_key,
    'DUCK-1' AS sku,
    '2026-03-10 10:00:00'::TIMESTAMPNTZ AS viewed_minute_utc,
    'Search' AS list_name,
    3 AS list_position
  UNION ALL
  SELECT
    'v1|DUCK-1|202603101001' AS product_view_key,
    'DUCK-1' AS sku,
    '2026-03-10 10:01:00'::TIMESTAMPNTZ AS viewed_minute_utc,
    CAST(NULL AS VARCHAR) AS list_name,
    CAST(NULL AS INT) AS list_position
)
