TEST (name "rpt_app_engagement_weekly__summarises_devices_and_push_starts_per_platform_week");

WITH __ref__int_app_sessions AS (
  SELECT
    'AS1' AS app_session_id,
    'D1' AS device_id,
    'C1' AS customer_id,
    'phone' AS platform,
    5 AS app_major_version,
    '2026-03-10 10:00:00'::TIMESTAMP_NTZ AS session_start_utc,
    NULL AS session_end_utc,
    100 AS duration_seconds,
    NULL AS event_count,
    NULL AS screen_count,
    TRUE AS started_from_push
  UNION ALL
  SELECT
    'AS2',
    'D1',
    NULL,
    'phone',
    6,
    '2026-03-11 10:00:00'::TIMESTAMP_NTZ,
    NULL,
    300,
    NULL,
    NULL,
    FALSE
  UNION ALL
  SELECT
    'AS3',
    'D2',
    'C2',
    'phone',
    5,
    '2026-03-12 10:00:00'::TIMESTAMP_NTZ,
    NULL,
    200,
    NULL,
    NULL,
    FALSE
  UNION ALL
  SELECT
    'AS4',
    'D3',
    NULL,
    'tablet',
    2,
    '2026-03-16 10:00:00'::TIMESTAMP_NTZ,
    NULL,
    50,
    NULL,
    NULL,
    TRUE
),

__expected__rpt_app_engagement_weekly AS (
  SELECT
    '2026-03-09:phone' AS app_week_key,
    3 AS sessions,
    2 AS active_devices,
    0.6667::DECIMAL(9, 4) AS signed_in_share,
    0.3333::DECIMAL(9, 4) AS push_started_share,
    200.0::DECIMAL(10, 2) AS median_session_seconds,
    6 AS latest_major_version
  UNION ALL
  SELECT
    '2026-03-16:tablet' AS app_week_key,
    1 AS sessions,
    1 AS active_devices,
    0.0::DECIMAL(9, 4) AS signed_in_share,
    1.0::DECIMAL(9, 4) AS push_started_share,
    50.0::DECIMAL(10, 2) AS median_session_seconds,
    2 AS latest_major_version
),

__assert__app_week_key_is_unique_and_present AS (
  SELECT t.app_week_key
  FROM __ref("rpt_app_engagement_weekly") AS t
  GROUP BY
    t.app_week_key
  HAVING
    COUNT(*) > 1
    OR t.app_week_key IS NULL
)
