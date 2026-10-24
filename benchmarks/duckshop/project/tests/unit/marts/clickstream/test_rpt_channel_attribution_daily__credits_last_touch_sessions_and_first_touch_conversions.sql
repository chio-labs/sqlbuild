TEST (name "rpt_channel_attribution_daily__credits_last_touch_sessions_and_first_touch_conversions");

WITH __ref__fct_web_sessions AS (
  SELECT
    'S1' AS session_id,
    'A1' AS anonymous_id,
    NULL AS customer_id,
    '2026-03-10 10:00:00'::TIMESTAMP_NTZ AS session_start_utc,
    NULL AS session_start_visitor_local,
    NULL AS duration_seconds,
    NULL AS page_view_count,
    NULL AS landing_page_path,
    'ORGANIC' AS channel_code,
    FALSE AS is_paid,
    NULL AS utm_campaign,
    'PAID_SOCIAL' AS first_touch_channel,
    NULL AS touch_number,
    NULL AS is_bounce,
    NULL AS funnel_stage,
    TRUE AS converted,
    NULL AS visitor_bucket
  UNION ALL
  SELECT
    'S2',
    'A2',
    NULL,
    '2026-03-10 10:00:00'::TIMESTAMP_NTZ,
    NULL,
    NULL,
    NULL,
    NULL,
    'ORGANIC',
    FALSE,
    NULL,
    'ORGANIC',
    NULL,
    NULL,
    NULL,
    FALSE,
    NULL
  UNION ALL
  SELECT
    'S3',
    'A1',
    NULL,
    '2026-03-10 10:00:00'::TIMESTAMP_NTZ,
    NULL,
    NULL,
    NULL,
    NULL,
    'PAID_SOCIAL',
    TRUE,
    NULL,
    'PAID_SOCIAL',
    NULL,
    NULL,
    NULL,
    FALSE,
    NULL
  UNION ALL
  SELECT
    'S4',
    'A3',
    NULL,
    '2026-03-10 10:00:00'::TIMESTAMP_NTZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    TRUE,
    NULL
),

__expected__rpt_channel_attribution_daily AS (
  SELECT
    '2026-03-10:ORGANIC' AS channel_day_key,
    2 AS sessions,
    2 AS visitors,
    1 AS conversions,
    0.5::DECIMAL(9, 4) AS conversion_rate,
    0 AS first_touch_credit,
    0.0::DECIMAL(9, 4) AS paid_share
  UNION ALL
  SELECT
    '2026-03-10:PAID_SOCIAL' AS channel_day_key,
    1 AS sessions,
    1 AS visitors,
    0 AS conversions,
    0.0::DECIMAL(9, 4) AS conversion_rate,
    1 AS first_touch_credit,
    1.0::DECIMAL(9, 4) AS paid_share
  UNION ALL
  SELECT
    '2026-03-10:UNKNOWN' AS channel_day_key,
    1 AS sessions,
    1 AS visitors,
    1 AS conversions,
    1.0::DECIMAL(9, 4) AS conversion_rate,
    1 AS first_touch_credit,
    0.0::DECIMAL(9, 4) AS paid_share
),

__assert__channel_day_key_is_unique_and_present AS (
  SELECT t.channel_day_key
  FROM __ref("rpt_channel_attribution_daily") AS t
  GROUP BY
    t.channel_day_key
  HAVING
    COUNT(*) > 1
    OR t.channel_day_key IS NULL
)
