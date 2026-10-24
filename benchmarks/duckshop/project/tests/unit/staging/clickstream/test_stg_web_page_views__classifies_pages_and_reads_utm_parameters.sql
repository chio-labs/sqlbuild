TEST (name "stg_web_page_views__classifies_pages_and_reads_utm_parameters");

WITH __ref__stg_web_events AS (
  SELECT
    'p1' AS event_id,
    NULL AS received_at,
    'page_view' AS event_type,
    '2026-03-10 10:00:00'::TIMESTAMP_NTZ AS event_at_utc,
    'v1' AS anonymous_id,
    NULL AS customer_id,
    NULL AS user_email,
    'https://shop.example.com/?utm_source=news&utm_medium=email&utm_campaign=spring#top' AS page_url,
    '/' AS page_path,
    NULL AS referrer_host,
    NULL AS user_agent,
    NULL AS locale,
    NULL AS client_timezone,
    FALSE AS is_bot,
    PARSE_JSON('{"title": "Home"}')::OBJECT AS properties,
    PARSE_JSON('[]')::ARRAY AS items
  UNION ALL
  SELECT
    'p2',
    NULL,
    'page_view',
    '2026-03-10 10:01:00'::TIMESTAMP_NTZ,
    'v1',
    NULL,
    NULL,
    'https://shop.example.com/products/duck-1',
    '/products/duck-1',
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
    PARSE_JSON('{}')::OBJECT,
    PARSE_JSON('[]')::ARRAY
  UNION ALL
  SELECT
    'p3',
    NULL,
    'page_view',
    '2026-03-10 10:02:00'::TIMESTAMP_NTZ,
    'v1',
    NULL,
    NULL,
    'https://shop.example.com/c/decoys',
    '/c/decoys',
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
    PARSE_JSON('{}')::OBJECT,
    PARSE_JSON('[]')::ARRAY
  UNION ALL
  SELECT
    'p4',
    NULL,
    'page_view',
    '2026-03-10 10:03:00'::TIMESTAMP_NTZ,
    'v1',
    NULL,
    NULL,
    'https://shop.example.com/checkout/step-1',
    '/checkout/step-1',
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
    PARSE_JSON('{}')::OBJECT,
    PARSE_JSON('[]')::ARRAY
  UNION ALL
  SELECT
    'p5',
    NULL,
    'page_view',
    '2026-03-10 10:04:00'::TIMESTAMP_NTZ,
    'v1',
    NULL,
    NULL,
    'https://shop.example.com/about',
    '/about',
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
    PARSE_JSON('{}')::OBJECT,
    PARSE_JSON('[]')::ARRAY
  UNION ALL
  SELECT
    'p6',
    NULL,
    'page_view',
    '2026-03-10 10:05:00'::TIMESTAMP_NTZ,
    'v1',
    NULL,
    NULL,
    'https://shop.example.com/',
    '/',
    NULL,
    NULL,
    NULL,
    NULL,
    TRUE,
    PARSE_JSON('{}')::OBJECT,
    PARSE_JSON('[]')::ARRAY
  UNION ALL
  SELECT
    'p7',
    NULL,
    'add_to_cart',
    '2026-03-10 10:06:00'::TIMESTAMP_NTZ,
    'v1',
    NULL,
    NULL,
    'https://shop.example.com/products/duck-1',
    '/products/duck-1',
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
    PARSE_JSON('{}')::OBJECT,
    PARSE_JSON('[]')::ARRAY
),

__expected__stg_web_page_views AS (
  SELECT
    'p1' AS event_id,
    'home' AS page_type,
    CAST(NULL AS VARCHAR) AS previous_page_path,
    'news' AS utm_source,
    'email' AS utm_medium,
    'spring' AS utm_campaign,
    'Home' AS page_title
  UNION ALL
  SELECT
    'p2' AS event_id,
    'product' AS page_type,
    '/' AS previous_page_path,
    CAST(NULL AS VARCHAR) AS utm_source,
    CAST(NULL AS VARCHAR) AS utm_medium,
    CAST(NULL AS VARCHAR) AS utm_campaign,
    CAST(NULL AS VARCHAR) AS page_title
  UNION ALL
  SELECT
    'p3' AS event_id,
    'category' AS page_type,
    '/products/duck-1' AS previous_page_path,
    CAST(NULL AS VARCHAR) AS utm_source,
    CAST(NULL AS VARCHAR) AS utm_medium,
    CAST(NULL AS VARCHAR) AS utm_campaign,
    CAST(NULL AS VARCHAR) AS page_title
  UNION ALL
  SELECT
    'p4' AS event_id,
    'checkout' AS page_type,
    '/c/decoys' AS previous_page_path,
    CAST(NULL AS VARCHAR) AS utm_source,
    CAST(NULL AS VARCHAR) AS utm_medium,
    CAST(NULL AS VARCHAR) AS utm_campaign,
    CAST(NULL AS VARCHAR) AS page_title
  UNION ALL
  SELECT
    'p5' AS event_id,
    'content' AS page_type,
    '/checkout/step-1' AS previous_page_path,
    CAST(NULL AS VARCHAR) AS utm_source,
    CAST(NULL AS VARCHAR) AS utm_medium,
    CAST(NULL AS VARCHAR) AS utm_campaign,
    CAST(NULL AS VARCHAR) AS page_title
)
