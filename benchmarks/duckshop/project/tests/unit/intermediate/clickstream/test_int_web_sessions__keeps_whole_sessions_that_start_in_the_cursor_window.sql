TEST (name "int_web_sessions__keeps_whole_sessions_that_start_in_the_cursor_window", cursor_start "2026-03-10", cursor_end "2026-03-11");

WITH __ref__stg_web_events AS (
  SELECT
    'e1' AS event_id,
    '2026-03-09 23:55:00'::TIMESTAMP_NTZ AS received_at,
    'page_view' AS event_type,
    '2026-03-09 23:50:00'::TIMESTAMP_NTZ AS event_at_utc,
    'V1' AS anonymous_id,
    NULL AS customer_id,
    NULL AS user_email,
    'https://shop.example.com/home' AS page_url,
    '/home' AS page_path,
    NULL AS referrer_host,
    NULL AS user_agent,
    NULL AS locale,
    'Europe/Berlin' AS client_timezone,
    FALSE AS is_bot,
    NULL AS properties,
    NULL AS items
  UNION ALL
  SELECT
    'e2',
    '2026-03-10 00:15:00'::TIMESTAMP_NTZ,
    'page_view',
    '2026-03-10 00:10:00'::TIMESTAMP_NTZ,
    'V1',
    NULL,
    NULL,
    'https://shop.example.com/sale',
    '/sale',
    NULL,
    NULL,
    NULL,
    'Europe/Berlin',
    FALSE,
    NULL,
    NULL
  UNION ALL
  SELECT
    'e3',
    '2026-03-11 00:05:00'::TIMESTAMP_NTZ,
    'page_view',
    '2026-03-10 23:59:00'::TIMESTAMP_NTZ,
    'V1',
    NULL,
    NULL,
    'https://shop.example.com/late',
    '/late',
    NULL,
    NULL,
    NULL,
    'Europe/Berlin',
    FALSE,
    NULL,
    NULL
  UNION ALL
  SELECT
    'e4',
    '2026-03-11 00:20:00'::TIMESTAMP_NTZ,
    'page_view',
    '2026-03-11 00:15:00'::TIMESTAMP_NTZ,
    'V1',
    NULL,
    NULL,
    'https://shop.example.com/after-midnight',
    '/after-midnight',
    NULL,
    NULL,
    NULL,
    'Europe/Berlin',
    FALSE,
    NULL,
    NULL
),

__expected__int_web_sessions AS (
  SELECT
    'V1:20260310235900' AS session_id,
    '2026-03-10 00:00:00'::TIMESTAMPNTZ AS session_day,
    2 AS event_count,
    '/late' AS landing_page_path
)
