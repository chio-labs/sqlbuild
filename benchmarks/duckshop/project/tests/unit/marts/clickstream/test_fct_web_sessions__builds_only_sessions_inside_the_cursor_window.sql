TEST (name "fct_web_sessions__builds_only_sessions_inside_the_cursor_window", cursor_start "2026-03-10 10:00:00", cursor_end "2026-03-10 11:00:00");

WITH __ref__int_web_sessions AS (
  SELECT
    'S1' AS session_id,
    'A1' AS anonymous_id,
    NULL AS customer_id,
    NULL AS session_day,
    '2026-03-10 09:30:00'::TIMESTAMP_NTZ AS session_start_utc,
    NULL AS session_end_utc,
    NULL AS session_start_visitor_local,
    NULL AS duration_seconds,
    NULL AS event_count,
    NULL AS page_view_count,
    NULL AS landing_page_path,
    NULL AS exit_page_path,
    NULL AS referrer_host,
    NULL AS landing_page_url,
    TRUE AS is_bounce,
    NULL AS has_add_to_cart,
    FALSE AS has_order
  UNION ALL
  SELECT
    'S2',
    'A2',
    NULL,
    NULL,
    '2026-03-10 10:15:00'::TIMESTAMP_NTZ,
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
    NULL,
    TRUE
  UNION ALL
  SELECT
    'S3',
    'A3',
    NULL,
    NULL,
    '2026-03-10 11:00:00'::TIMESTAMP_NTZ,
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
    NULL,
    TRUE
),

__ref__int_session_attribution AS (
  SELECT
    'S1' AS session_id,
    NULL AS anonymous_id,
    NULL AS customer_id,
    NULL AS session_start_utc,
    NULL AS utm_source,
    NULL AS utm_medium,
    NULL AS utm_campaign,
    'ORGANIC' AS channel_code,
    FALSE AS is_paid,
    'PAID_SOCIAL' AS first_touch_channel,
    NULL AS last_touch_channel,
    2 AS touch_number
),

__ref__int_cart_funnel AS (
  SELECT
    'S2' AS session_id,
    NULL AS anonymous_id,
    NULL AS session_start_utc,
    NULL AS added_skus,
    NULL AS removed_sku_count,
    NULL AS net_units,
    NULL AS max_added_unit_minor,
    NULL AS reached_checkout,
    NULL AS reached_payment,
    TRUE AS converted,
    'purchase' AS funnel_stage
),

__expected__fct_web_sessions AS (
  SELECT
    'S2' AS session_id,
    'purchase' AS funnel_stage
),

__assert__session_id_is_unique_and_present AS (
  SELECT t.session_id
  FROM __ref("fct_web_sessions") AS t
  GROUP BY
    t.session_id
  HAVING
    COUNT(*) > 1
    OR t.session_id IS NULL
)
