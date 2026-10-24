TEST (name "int_subscription_periods__splits_pause_and_cancel_into_periods");

WITH __ref__stg_subscriptions AS (
  SELECT
    'S1' AS subscription_id,
    'C1' AS customer_id,
    NULL AS plan_code,
    NULL AS sku,
    30 AS interval_days,
    NULL AS subscription_status,
    '2026-01-01 00:00:00 +00:00'::TIMESTAMP_TZ AS started_at,
    NULL AS cancelled_at,
    2000 AS billing_amount_minor,
    'EUR' AS billing_currency_code,
    NULL AS next_bill_on,
    NULL AS billing,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__ref__stg_subscription_events AS (
  SELECT
    'E1' AS event_id,
    'S1' AS subscription_id,
    'PAUSE' AS event_type,
    '2026-01-11 00:00:00 +00:00'::TIMESTAMP_TZ AS occurred_at,
    NULL AS pause_days,
    NULL AS skip_reason,
    NULL AS payload,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'E2',
    'S1',
    'RESUME',
    '2026-01-16 12:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'E3',
    'S1',
    'SKIP',
    '2026-01-20 00:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'E4',
    'S1',
    'CANCEL',
    '2026-02-01 00:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__expected__int_subscription_periods AS (
  SELECT
    'S1#1' AS subscription_period_key,
    1 AS period_number,
    'active' AS period_state,
    10.0::DECIMAL(10, 2) AS period_days
  UNION ALL
  SELECT
    'S1#2' AS subscription_period_key,
    2 AS period_number,
    'paused' AS period_state,
    5.5::DECIMAL(10, 2) AS period_days
  UNION ALL
  SELECT
    'S1#3' AS subscription_period_key,
    3 AS period_number,
    'active' AS period_state,
    15.5::DECIMAL(10, 2) AS period_days
  UNION ALL
  SELECT
    'S1#4' AS subscription_period_key,
    4 AS period_number,
    'cancelled' AS period_state,
    0.0::DECIMAL(10, 2) AS period_days
)
