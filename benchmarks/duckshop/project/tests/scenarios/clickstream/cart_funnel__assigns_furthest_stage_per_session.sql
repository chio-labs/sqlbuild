SCENARIO (
  description "Cart events and checkout steps place each web session at its furthest funnel stage",
  tags ["clickstream", "funnel"],
  timeout "5m",
);

WITH __ref__int_web_sessions AS (
  SELECT
    'S1' AS session_id,
    'V1' AS anonymous_id,
    NULL AS customer_id,
    NULL AS session_day,
    '2026-03-10 10:00:00'::TIMESTAMP_NTZ AS session_start_utc,
    '2026-03-10 10:30:00'::TIMESTAMP_NTZ AS session_end_utc,
    NULL AS session_start_visitor_local,
    NULL AS duration_seconds,
    NULL AS event_count,
    NULL AS page_view_count,
    NULL AS landing_page_path,
    NULL AS exit_page_path,
    NULL AS referrer_host,
    NULL AS landing_page_url,
    FALSE AS is_bounce,
    TRUE AS has_add_to_cart,
    FALSE AS has_order
  UNION ALL
  SELECT
    'S2',
    'V1',
    NULL,
    NULL,
    '2026-03-10 12:00:00'::TIMESTAMP_NTZ,
    '2026-03-10 12:20:00'::TIMESTAMP_NTZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
    FALSE,
    TRUE
  UNION ALL
  SELECT
    'S3',
    'V2',
    NULL,
    NULL,
    '2026-03-10 10:00:00'::TIMESTAMP_NTZ,
    '2026-03-10 10:05:00'::TIMESTAMP_NTZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
    FALSE,
    FALSE
),

__ref__stg_web_events AS (
  SELECT
    'e1' AS event_id,
    '2026-03-10 10:05:00'::TIMESTAMP_NTZ AS received_at,
    'add_to_cart' AS event_type,
    '2026-03-10 10:05:00'::TIMESTAMP_NTZ AS event_at_utc,
    'V1' AS anonymous_id,
    NULL AS customer_id,
    NULL AS user_email,
    NULL AS page_url,
    NULL AS page_path,
    NULL AS referrer_host,
    NULL AS user_agent,
    NULL AS locale,
    'Europe/Berlin' AS client_timezone,
    FALSE AS is_bot,
    NULL AS properties,
    ARRAY_CONSTRUCT(
      OBJECT_CONSTRUCT(
        'sku',
        'duck-1',
        'quantity',
        2,
        'price_minor',
        500
      ),
      OBJECT_CONSTRUCT('sku', 'DUCK-2', 'price_minor', 900),
      OBJECT_CONSTRUCT('quantity', 1, 'price_minor', 100),
      OBJECT_CONSTRUCT('sku', 'duck-3', 'quantity', 0)
    )::ARRAY AS items
  UNION ALL
  SELECT
    'e2',
    '2026-03-10 10:10:00'::TIMESTAMP_NTZ,
    'remove_from_cart',
    '2026-03-10 10:10:00'::TIMESTAMP_NTZ,
    'V1',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'Europe/Berlin',
    FALSE,
    NULL,
    ARRAY_CONSTRUCT(
      OBJECT_CONSTRUCT('sku', 'duck-1', 'quantity', 1)
    )::ARRAY
  UNION ALL
  SELECT
    'e3',
    '2026-03-10 10:20:00'::TIMESTAMP_NTZ,
    'add_to_cart',
    '2026-03-10 10:20:00'::TIMESTAMP_NTZ,
    'V1',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'Europe/Berlin',
    FALSE,
    NULL,
    ARRAY_CONSTRUCT(
      OBJECT_CONSTRUCT(
        'sku',
        'DUCK-1',
        'quantity',
        1,
        'price_minor',
        500
      )
    )::ARRAY
  UNION ALL
  SELECT
    'e4',
    '2026-03-10 11:00:00'::TIMESTAMP_NTZ,
    'add_to_cart',
    '2026-03-10 11:00:00'::TIMESTAMP_NTZ,
    'V1',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'Europe/Berlin',
    FALSE,
    NULL,
    ARRAY_CONSTRUCT(
      OBJECT_CONSTRUCT('sku', 'DUCK-9', 'price_minor', 9900)
    )::ARRAY
),

__ref__stg_web_checkout_steps AS (
  SELECT
    'V1:1' AS checkout_step_key,
    'V1' AS anonymous_id,
    1 AS step_number,
    NULL AS step_name,
    '2026-03-10 10:25:00'::TIMESTAMP_NTZ AS first_reached_at_utc,
    NULL AS payment_option
  UNION ALL
  SELECT
    'V1:2',
    'V1',
    2,
    NULL,
    '2026-03-10 10:26:00'::TIMESTAMP_NTZ,
    NULL
  UNION ALL
  SELECT
    'V1:3',
    'V1',
    3,
    NULL,
    '2026-03-10 12:10:00'::TIMESTAMP_NTZ,
    NULL
),

__expected__int_cart_funnel AS (
  SELECT
    'S1' AS session_id,
    1 AS removed_sku_count,
    3 AS net_units,
    900 AS max_added_unit_minor,
    TRUE AS reached_checkout,
    FALSE AS reached_payment,
    FALSE AS converted,
    'checkout' AS funnel_stage
  UNION ALL
  SELECT
    'S2' AS session_id,
    0 AS removed_sku_count,
    0 AS net_units,
    CAST(NULL AS INT) AS max_added_unit_minor,
    TRUE AS reached_checkout,
    TRUE AS reached_payment,
    TRUE AS converted,
    'order' AS funnel_stage
  UNION ALL
  SELECT
    'S3' AS session_id,
    0 AS removed_sku_count,
    0 AS net_units,
    CAST(NULL AS INT) AS max_added_unit_minor,
    FALSE AS reached_checkout,
    FALSE AS reached_payment,
    FALSE AS converted,
    'browse' AS funnel_stage
),

__assert__added_skus_are_upper_cased_and_distinct AS (
  SELECT f.session_id
  FROM __ref("int_cart_funnel") AS f
  WHERE ARRAY_TO_STRING(f.added_skus, ',') <> IFF(f.session_id = 'S1', 'DUCK-1,DUCK-2', '')
)
