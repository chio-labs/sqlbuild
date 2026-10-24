TEST (name "int_order_status_timeline__builds_milestones_and_detects_regressions");

WITH __ref__stg_order_status_events AS (
  SELECT
    'E1' AS event_id,
    'O1' AS order_id,
    NULL AS from_status,
    'paid' AS to_status,
    '2026-03-01 10:30:00 +00:00'::TIMESTAMP_TZ AS changed_at,
    NULL AS actor_type,
    NULL AS actor_id,
    NULL AS actor,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'E2',
    'O1',
    NULL,
    'shipped',
    '2026-03-02 10:30:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'E3',
    'O1',
    NULL,
    'packed',
    '2026-03-02 11:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'E4',
    'O1',
    NULL,
    'delivered',
    '2026-03-04 10:30:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'E5',
    'O2',
    NULL,
    'cancelled',
    '2026-03-01 12:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_orders AS (
  SELECT
    'O1' AS order_id,
    NULL AS customer_id,
    NULL AS storefront_code,
    NULL AS currency_code,
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ AS placed_at,
    NULL AS order_status,
    NULL AS sales_channel,
    NULL AS is_gift,
    NULL AS utm_source,
    NULL AS utm_medium,
    NULL AS utm_campaign,
    NULL AS device_type,
    NULL AS item_count_hint,
    NULL AS shipping_address_id,
    NULL AS attributes,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'O2',
    NULL,
    NULL,
    NULL,
    '2026-03-01 11:00:00 +00:00'::TIMESTAMP_TZ,
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
    NULL
),

__expected__int_order_status_timeline AS (
  SELECT
    'O1' AS order_id,
    4 AS transition_count,
    30 AS minutes_to_pay,
    24.0::DECIMAL(12, 2) AS hours_paid_to_shipped,
    'paid > shipped > packed > delivered' AS status_path,
    TRUE AS has_regression,
    'delivered' AS last_status,
    'packed' AS longest_status
  UNION ALL
  SELECT
    'O2' AS order_id,
    1 AS transition_count,
    CAST(NULL AS INT) AS minutes_to_pay,
    CAST(NULL AS DECIMAL(12, 2)) AS hours_paid_to_shipped,
    'cancelled' AS status_path,
    FALSE AS has_regression,
    'cancelled' AS last_status,
    'cancelled' AS longest_status
)
