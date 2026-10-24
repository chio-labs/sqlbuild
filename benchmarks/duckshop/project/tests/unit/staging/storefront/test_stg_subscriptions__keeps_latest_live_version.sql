TEST (name "stg_subscriptions__keeps_latest_live_version");

WITH __source__storefront__subscriptions AS (
  SELECT
    'K1' AS subscription_id,
    NULL AS customer_id,
    NULL AS plan_code,
    NULL AS sku,
    NULL AS interval_days,
    NULL AS subscription_status,
    NULL AS started_at,
    NULL AS cancelled_at,
    NULL AS billing,
    'I' AS _op,
    1 AS _seq,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'K1',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'U',
    2,
    '2026-01-02 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'K2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'I',
    3,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'K2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'D',
    4,
    '2026-01-03 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_subscriptions AS (
  SELECT
    'K1' AS subscription_id,
    2 AS source_seq
)
