TEST (name "stg_app_screen_views__caps_time_on_screen_at_thirty_minutes");

WITH __ref__stg_app_events AS (
  SELECT
    's1' AS event_id,
    NULL AS received_at,
    'phone' AS platform,
    NULL AS app_version,
    NULL AS app_major_version,
    'screen_view' AS event_name,
    '2026-03-10 10:00:00'::TIMESTAMP_NTZ AS event_at_utc,
    'D1' AS device_id,
    NULL AS customer_id,
    'product_detail' AS screen_name,
    PARSE_JSON('{"screen_class": "PdpVC"}')::OBJECT AS attributes
  UNION ALL
  SELECT
    'e2',
    NULL,
    'phone',
    NULL,
    NULL,
    'push_open',
    '2026-03-10 10:00:30'::TIMESTAMP_NTZ,
    'D1',
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    's3',
    NULL,
    'phone',
    NULL,
    NULL,
    'screen_view',
    '2026-03-10 10:01:00'::TIMESTAMP_NTZ,
    'D1',
    NULL,
    'cart',
    NULL
  UNION ALL
  SELECT
    's4',
    NULL,
    'phone',
    NULL,
    NULL,
    'screen_view',
    '2026-03-10 11:00:00'::TIMESTAMP_NTZ,
    'D1',
    NULL,
    'home',
    NULL
  UNION ALL
  SELECT
    's5',
    NULL,
    'phone',
    NULL,
    NULL,
    'screen_view',
    '2026-03-10 12:00:00'::TIMESTAMP_NTZ,
    'D1',
    NULL,
    'home',
    NULL
  UNION ALL
  SELECT
    's6',
    NULL,
    'phone',
    NULL,
    NULL,
    'screen_view',
    '2026-03-10 12:00:00'::TIMESTAMP_NTZ,
    NULL,
    NULL,
    'home',
    NULL
),

__expected__stg_app_screen_views AS (
  SELECT
    's1' AS event_id,
    'Product Detail' AS screen_name,
    30 AS seconds_on_screen,
    'PdpVC' AS screen_class
  UNION ALL
  SELECT
    's3' AS event_id,
    'Cart' AS screen_name,
    1800 AS seconds_on_screen,
    CAST(NULL AS VARCHAR) AS screen_class
  UNION ALL
  SELECT
    's4' AS event_id,
    'Home' AS screen_name,
    1800 AS seconds_on_screen,
    CAST(NULL AS VARCHAR) AS screen_class
  UNION ALL
  SELECT
    's5' AS event_id,
    'Home' AS screen_name,
    CAST(NULL AS INT) AS seconds_on_screen,
    CAST(NULL AS VARCHAR) AS screen_class
)
