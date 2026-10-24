TEST (name "stg_web_identifies__links_visitors_to_customers_with_methods");

WITH __ref__stg_web_events AS (
  SELECT
    'i1' AS event_id,
    NULL AS received_at,
    'login' AS event_type,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ AS event_at_utc,
    'v1' AS anonymous_id,
    'C1' AS customer_id,
    NULL AS user_email,
    NULL AS page_url,
    NULL AS page_path,
    NULL AS referrer_host,
    NULL AS user_agent,
    NULL AS locale,
    NULL AS client_timezone,
    FALSE AS is_bot,
    PARSE_JSON('{"method": "password"}')::OBJECT AS properties,
    PARSE_JSON('[]')::ARRAY AS items
  UNION ALL
  SELECT
    'i2',
    NULL,
    'order_completed',
    '2026-03-05 10:00:00'::TIMESTAMP_NTZ,
    'v1',
    'C1',
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
    'i3',
    NULL,
    'identify',
    '2026-03-03 10:00:00'::TIMESTAMP_NTZ,
    'v1',
    'C1',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
    PARSE_JSON('{"method": "password"}')::OBJECT,
    PARSE_JSON('[]')::ARRAY
  UNION ALL
  SELECT
    'i4',
    NULL,
    'signup',
    '2026-03-06 10:00:00'::TIMESTAMP_NTZ,
    'v1',
    'C2',
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
    'i5',
    NULL,
    'login',
    '2026-03-06 10:00:00'::TIMESTAMP_NTZ,
    'v2',
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
    'i6',
    NULL,
    'page_view',
    '2026-03-06 10:00:00'::TIMESTAMP_NTZ,
    'v1',
    'C1',
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
),

__expected__stg_web_identifies AS (
  SELECT
    'v1>C1' AS identity_link_key,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ AS first_seen_at_utc,
    '2026-03-05 10:00:00'::TIMESTAMP_NTZ AS last_seen_at_utc,
    3 AS event_count
  UNION ALL
  SELECT
    'v1>C2' AS identity_link_key,
    '2026-03-06 10:00:00'::TIMESTAMP_NTZ AS first_seen_at_utc,
    '2026-03-06 10:00:00'::TIMESTAMP_NTZ AS last_seen_at_utc,
    1 AS event_count
),

__assert__identify_methods_are_distinct_and_sorted AS (
  SELECT i.identity_link_key
  FROM __ref("stg_web_identifies") AS i
  WHERE
    ARRAY_TO_STRING(i.identify_methods, ',') <> IFF(
      i.customer_id = 'C1',
      'order_completed,password',
      'signup'
    )
)
