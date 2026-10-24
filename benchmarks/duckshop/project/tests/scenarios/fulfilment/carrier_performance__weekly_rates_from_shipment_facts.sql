SCENARIO (
  description "Shipment facts feed weekly carrier dispatch, delivery-time and exception measures",
  tags ["fulfilment", "carriers"],
);

WITH __ref__stg_shipments AS (
  SELECT
    'S1' AS shipment_id,
    'O-S1' AS order_id,
    'POND' AS warehouse_code,
    'FLAPWING' AS carrier_code,
    'STANDARD' AS service_level,
    NULL AS tracking_number,
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ AS shipped_at,
    NULL AS delivered_at,
    1 AS tracking_event_count,
    NULL AS tracking_events,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'S2',
    'O-S2',
    'POND',
    'FLAPWING',
    'STANDARD',
    NULL,
    '2026-03-11 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    1,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'S3',
    'O-S3',
    'POND',
    'FLAPWING',
    'STANDARD',
    NULL,
    '2026-03-15 23:30:00 -02:00'::TIMESTAMP_TZ,
    NULL,
    1,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'S4',
    'O-S4',
    'POND',
    'FLAPWING',
    'STANDARD',
    NULL,
    NULL,
    NULL,
    1,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'S5',
    'O-S5',
    'POND',
    'WINGBEAT',
    'STANDARD',
    NULL,
    '2026-03-12 08:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    1,
    NULL,
    NULL,
    NULL
),

__ref__int_fulfilment_sla AS (
  SELECT
    'S1' AS shipment_id,
    NULL AS order_id,
    NULL AS warehouse_code,
    NULL AS carrier_code,
    NULL AS placed_at_local,
    NULL AS shipped_at_local,
    NULL AS calendar_days_to_ship,
    NULL AS business_days_to_ship,
    NULL AS holidays_in_window,
    NULL AS dispatch_business_minutes,
    TRUE AS is_dispatch_on_time,
    NULL AS delivered_at_utc,
    24.0::DECIMAL(10, 2) AS hours_to_deliver
  UNION ALL
  SELECT
    'S2',
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
    48.0::DECIMAL(10, 2)
  UNION ALL
  SELECT
    'S3',
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
    NULL,
    NULL
  UNION ALL
  SELECT
    'S5',
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
    NULL,
    10.0::DECIMAL(10, 2)
),

__ref__int_shipment_costs AS (
  SELECT
    'PK1' AS package_id,
    'S1' AS shipment_id,
    NULL AS carrier_code,
    NULL AS service_level,
    1.5::DECIMAL(10, 3) AS chargeable_weight_kg,
    NULL AS weight_basis,
    NULL AS band_max_kg,
    600 AS rate_minor,
    NULL AS rate_currency_code,
    NULL AS has_rate
),

__ref__int_delivery_exceptions_classified AS (
  SELECT
    'X1' AS exception_id,
    'S2' AS shipment_id,
    NULL AS carrier_code,
    NULL AS exception_code,
    NULL AS responsibility,
    NULL AS occurred_at,
    NULL AS hours_to_resolve,
    NULL AS resolution_type,
    5.5::DECIMAL(18, 2) AS compensation_usd,
    NULL AS exception_rank_in_shipment
),

__expected__fct_shipments AS (
  SELECT
    'S1' AS shipment_id,
    1 AS package_count,
    0 AS exception_count,
    0.0::DECIMAL(18, 2) AS compensation_usd
  UNION ALL
  SELECT
    'S2' AS shipment_id,
    0 AS package_count,
    1 AS exception_count,
    5.5::DECIMAL(18, 2) AS compensation_usd
  UNION ALL
  SELECT
    'S3' AS shipment_id,
    0 AS package_count,
    0 AS exception_count,
    0.0::DECIMAL(18, 2) AS compensation_usd
  UNION ALL
  SELECT
    'S4' AS shipment_id,
    0 AS package_count,
    0 AS exception_count,
    0.0::DECIMAL(18, 2) AS compensation_usd
  UNION ALL
  SELECT
    'S5' AS shipment_id,
    0 AS package_count,
    0 AS exception_count,
    0.0::DECIMAL(18, 2) AS compensation_usd
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
)
