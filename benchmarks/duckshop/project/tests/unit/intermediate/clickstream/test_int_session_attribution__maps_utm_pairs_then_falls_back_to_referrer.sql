TEST (name "int_session_attribution__maps_utm_pairs_then_falls_back_to_referrer");

WITH __ref__int_web_sessions AS (
  SELECT
    'S1' AS session_id,
    'V1' AS anonymous_id,
    NULL AS customer_id,
    NULL AS session_day,
    '2026-03-10 08:00:00'::TIMESTAMP_NTZ AS session_start_utc,
    '2026-03-10 08:10:00'::TIMESTAMP_NTZ AS session_end_utc,
    NULL AS session_start_visitor_local,
    NULL AS duration_seconds,
    NULL AS event_count,
    NULL AS page_view_count,
    NULL AS landing_page_path,
    NULL AS exit_page_path,
    NULL AS referrer_host,
    'https://shop.example.com/?utm_source=Search_Ads&utm_medium=CPC&utm_campaign=Spring' AS landing_page_url,
    NULL AS is_bounce,
    FALSE AS has_add_to_cart,
    FALSE AS has_order
  UNION ALL
  SELECT
    'S2',
    'V1',
    NULL,
    NULL,
    '2026-03-10 09:00:00'::TIMESTAMP_NTZ,
    '2026-03-10 09:10:00'::TIMESTAMP_NTZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'https://shop.example.com/?utm_source=weekly&utm_medium=email',
    NULL,
    FALSE,
    FALSE
  UNION ALL
  SELECT
    'S3',
    'V1',
    NULL,
    NULL,
    '2026-03-10 10:00:00'::TIMESTAMP_NTZ,
    '2026-03-10 10:10:00'::TIMESTAMP_NTZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'blog.example.org',
    'https://shop.example.com/home',
    NULL,
    FALSE,
    FALSE
  UNION ALL
  SELECT
    'S4',
    'V2',
    NULL,
    NULL,
    '2026-03-10 10:00:00'::TIMESTAMP_NTZ,
    '2026-03-10 10:10:00'::TIMESTAMP_NTZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'https://shop.example.com/home',
    NULL,
    FALSE,
    FALSE
),

__seed__channel_mapping AS (
  SELECT
    'search_ads' AS utm_source,
    'cpc' AS utm_medium,
    'PAID_SEARCH' AS channel_code,
    TRUE AS is_paid
  UNION ALL
  SELECT
    '-',
    'email',
    'EMAIL',
    FALSE
  UNION ALL
  SELECT
    'social_ads',
    'paid_social',
    'PAID_SOCIAL',
    TRUE
),

__expected__int_session_attribution AS (
  SELECT
    'S1' AS session_id,
    'search_ads' AS utm_source,
    'cpc' AS utm_medium,
    'spring' AS utm_campaign,
    'PAID_SEARCH' AS channel_code,
    TRUE AS is_paid,
    'PAID_SEARCH' AS first_touch_channel,
    'REFERRAL' AS last_touch_channel,
    1 AS touch_number
  UNION ALL
  SELECT
    'S2' AS session_id,
    'weekly' AS utm_source,
    'email' AS utm_medium,
    CAST(NULL AS VARCHAR) AS utm_campaign,
    'EMAIL' AS channel_code,
    FALSE AS is_paid,
    'PAID_SEARCH' AS first_touch_channel,
    'REFERRAL' AS last_touch_channel,
    2 AS touch_number
  UNION ALL
  SELECT
    'S3' AS session_id,
    CAST(NULL AS VARCHAR) AS utm_source,
    CAST(NULL AS VARCHAR) AS utm_medium,
    CAST(NULL AS VARCHAR) AS utm_campaign,
    'REFERRAL' AS channel_code,
    FALSE AS is_paid,
    'PAID_SEARCH' AS first_touch_channel,
    'REFERRAL' AS last_touch_channel,
    3 AS touch_number
  UNION ALL
  SELECT
    'S4' AS session_id,
    CAST(NULL AS VARCHAR) AS utm_source,
    CAST(NULL AS VARCHAR) AS utm_medium,
    CAST(NULL AS VARCHAR) AS utm_campaign,
    'DIRECT' AS channel_code,
    FALSE AS is_paid,
    'DIRECT' AS first_touch_channel,
    'DIRECT' AS last_touch_channel,
    1 AS touch_number
)
