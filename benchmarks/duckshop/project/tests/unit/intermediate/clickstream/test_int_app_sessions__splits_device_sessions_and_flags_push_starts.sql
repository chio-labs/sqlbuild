TEST (name "int_app_sessions__splits_device_sessions_and_flags_push_starts");

WITH __ref__stg_app_events AS (
  SELECT
    'a1' AS event_id,
    NULL AS received_at,
    'phone' AS platform,
    NULL AS app_version,
    5 AS app_major_version,
    'push_open' AS event_name,
    '2026-03-10 08:00:00'::TIMESTAMP_NTZ AS event_at_utc,
    'D1' AS device_id,
    NULL AS customer_id,
    NULL AS screen_name,
    NULL AS attributes
  UNION ALL
  SELECT
    'a2',
    NULL,
    'phone',
    NULL,
    5,
    'screen_view',
    '2026-03-10 08:05:00'::TIMESTAMP_NTZ,
    'D1',
    'C1',
    NULL,
    NULL
  UNION ALL
  SELECT
    'a3',
    NULL,
    'phone',
    NULL,
    6,
    'screen_view',
    '2026-03-10 08:50:00'::TIMESTAMP_NTZ,
    'D1',
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'a4',
    NULL,
    'phone',
    NULL,
    5,
    'screen_view',
    '2026-03-10 08:51:00'::TIMESTAMP_NTZ,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'b1',
    NULL,
    'tablet',
    NULL,
    5,
    'screen_view',
    '2026-03-10 09:00:00'::TIMESTAMP_NTZ,
    'D2',
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'b2',
    NULL,
    'tablet',
    NULL,
    5,
    'push_open',
    '2026-03-10 09:10:00'::TIMESTAMP_NTZ,
    'D2',
    NULL,
    NULL,
    NULL
),

__expected__int_app_sessions AS (
  SELECT
    'D1:20260310080000' AS app_session_id,
    'C1' AS customer_id,
    'phone' AS platform,
    5 AS app_major_version,
    300 AS duration_seconds,
    2 AS event_count,
    1 AS screen_count,
    TRUE AS started_from_push
  UNION ALL
  SELECT
    'D1:20260310085000' AS app_session_id,
    CAST(NULL AS VARCHAR) AS customer_id,
    'phone' AS platform,
    6 AS app_major_version,
    0 AS duration_seconds,
    1 AS event_count,
    1 AS screen_count,
    FALSE AS started_from_push
  UNION ALL
  SELECT
    'D2:20260310090000' AS app_session_id,
    CAST(NULL AS VARCHAR) AS customer_id,
    'tablet' AS platform,
    5 AS app_major_version,
    600 AS duration_seconds,
    2 AS event_count,
    1 AS screen_count,
    FALSE AS started_from_push
)
