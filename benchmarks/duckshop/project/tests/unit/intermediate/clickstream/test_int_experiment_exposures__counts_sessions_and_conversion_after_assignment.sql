TEST (name "int_experiment_exposures__counts_sessions_and_conversion_after_assignment");

WITH __ref__stg_experiment_assignments AS (
  SELECT
    'A1' AS assignment_id,
    'checkout_v2' AS experiment_key,
    'control' AS variant_key,
    'V1' AS anonymous_id,
    NULL AS customer_id,
    '2026-03-10 10:00:00 +01:00'::TIMESTAMP_TZ AS assigned_at,
    'web' AS assignment_surface,
    NULL AS context
  UNION ALL
  SELECT
    'A2',
    'checkout_v2',
    'treatment',
    'V2',
    NULL,
    '2026-03-10 09:00:00 +00:00'::TIMESTAMP_TZ,
    'web',
    NULL
  UNION ALL
  SELECT
    'A3',
    'checkout_v2',
    'b',
    'V3',
    NULL,
    '2026-03-10 09:00:00 +00:00'::TIMESTAMP_TZ,
    'app',
    NULL
),

__ref__int_web_sessions AS (
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
    NULL AS landing_page_url,
    NULL AS is_bounce,
    FALSE AS has_add_to_cart,
    TRUE AS has_order
  UNION ALL
  SELECT
    'S2',
    'V1',
    NULL,
    NULL,
    '2026-03-10 09:30:00'::TIMESTAMP_NTZ,
    '2026-03-10 09:40:00'::TIMESTAMP_NTZ,
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
    FALSE
  UNION ALL
  SELECT
    'S3',
    'V1',
    NULL,
    NULL,
    '2026-03-11 21:00:00'::TIMESTAMP_NTZ,
    '2026-03-11 21:10:00'::TIMESTAMP_NTZ,
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
    TRUE
  UNION ALL
  SELECT
    'S4',
    'V2',
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
    NULL,
    NULL,
    FALSE,
    TRUE
),

__expected__int_experiment_exposures AS (
  SELECT
    'A1' AS assignment_id,
    TRUE AS is_control,
    '2026-03-10 09:00:00'::TIMESTAMPNTZ AS assigned_at_utc,
    2 AS sessions_after,
    TRUE AS converted,
    1.5::DECIMAL(10, 2) AS days_to_convert
  UNION ALL
  SELECT
    'A2' AS assignment_id,
    FALSE AS is_control,
    '2026-03-10 09:00:00'::TIMESTAMPNTZ AS assigned_at_utc,
    1 AS sessions_after,
    TRUE AS converted,
    0.0::DECIMAL(10, 2) AS days_to_convert
  UNION ALL
  SELECT
    'A3' AS assignment_id,
    FALSE AS is_control,
    '2026-03-10 09:00:00'::TIMESTAMPNTZ AS assigned_at_utc,
    0 AS sessions_after,
    FALSE AS converted,
    CAST(NULL AS DECIMAL(10, 2)) AS days_to_convert
)
