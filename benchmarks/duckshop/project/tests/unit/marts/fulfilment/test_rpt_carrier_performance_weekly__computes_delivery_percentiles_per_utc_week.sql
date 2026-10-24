TEST (name "rpt_carrier_performance_weekly__computes_delivery_percentiles_per_utc_week");

WITH __ref__fct_shipments AS (
  SELECT
    'S1' AS shipment_id,
    NULL AS order_id,
    NULL AS fulfilment_method,
    NULL AS warehouse_code,
    'FLAPWING' AS carrier_code,
    NULL AS service_level,
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ AS shipped_at,
    NULL AS delivered_at,
    NULL AS business_days_to_ship,
    TRUE AS is_dispatch_on_time,
    24.0::NUMBER(10, 2) AS hours_to_deliver,
    NULL AS package_count,
    NULL AS chargeable_weight_kg,
    NULL AS rate_minor,
    0 AS exception_count,
    0.0::DECIMAL(18, 2) AS compensation_usd,
    NULL AS tracking_event_count
  UNION ALL
  SELECT
    'S2',
    NULL,
    NULL,
    NULL,
    'FLAPWING',
    NULL,
    '2026-03-11 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    FALSE,
    48.0::NUMBER(10, 2),
    NULL,
    NULL,
    NULL,
    1,
    5.5::DECIMAL(18, 2),
    NULL
  UNION ALL
  SELECT
    'S3',
    NULL,
    NULL,
    NULL,
    'FLAPWING',
    NULL,
    '2026-03-15 23:30:00 -02:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    TRUE,
    NULL,
    NULL,
    NULL,
    NULL,
    0,
    0.0::DECIMAL(18, 2),
    NULL
  UNION ALL
  SELECT
    'S4',
    NULL,
    NULL,
    NULL,
    'FLAPWING',
    NULL,
    NULL,
    NULL,
    NULL,
    TRUE,
    NULL,
    NULL,
    NULL,
    NULL,
    0,
    0.0::DECIMAL(18, 2),
    NULL
  UNION ALL
  SELECT
    'S5',
    NULL,
    NULL,
    NULL,
    'WINGBEAT',
    NULL,
    '2026-03-12 08:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    TRUE,
    10.0::NUMBER(10, 2),
    NULL,
    NULL,
    NULL,
    0,
    0.0::DECIMAL(18, 2),
    NULL
),

__expected__rpt_carrier_performance_weekly AS (
  SELECT
    'FLAPWING:2026-03-09' AS carrier_week_key,
    2 AS shipments,
    0.5::DECIMAL(9, 4) AS on_time_dispatch_rate,
    36.0::DECIMAL(10, 2) AS p50_hours_to_deliver,
    45.6::DECIMAL(10, 2) AS p90_hours_to_deliver,
    0.5::DECIMAL(9, 4) AS exception_rate,
    5.5::DECIMAL(18, 2) AS compensation_usd
  UNION ALL
  SELECT
    'FLAPWING:2026-03-16' AS carrier_week_key,
    1 AS shipments,
    1.0::DECIMAL(9, 4) AS on_time_dispatch_rate,
    CAST(NULL AS DECIMAL(10, 2)) AS p50_hours_to_deliver,
    CAST(NULL AS DECIMAL(10, 2)) AS p90_hours_to_deliver,
    0.0::DECIMAL(9, 4) AS exception_rate,
    0.0::DECIMAL(18, 2) AS compensation_usd
  UNION ALL
  SELECT
    'WINGBEAT:2026-03-09' AS carrier_week_key,
    1 AS shipments,
    1.0::DECIMAL(9, 4) AS on_time_dispatch_rate,
    10.0::DECIMAL(10, 2) AS p50_hours_to_deliver,
    10.0::DECIMAL(10, 2) AS p90_hours_to_deliver,
    0.0::DECIMAL(9, 4) AS exception_rate,
    0.0::DECIMAL(18, 2) AS compensation_usd
),

__assert__carrier_week_key_is_unique_and_present AS (
  SELECT t.carrier_week_key
  FROM __ref("rpt_carrier_performance_weekly") AS t
  GROUP BY
    t.carrier_week_key
  HAVING
    COUNT(*) > 1
    OR t.carrier_week_key IS NULL
)
