TEST (name "fct_shipments__classifies_fulfilment_and_totals_packages_and_exceptions");

WITH __ref__stg_shipments AS (
  SELECT
    'S1' AS shipment_id,
    'O1' AS order_id,
    'POND' AS warehouse_code,
    'FLAPWING' AS carrier_code,
    'STANDARD' AS service_level,
    NULL AS tracking_number,
    NULL AS shipped_at,
    NULL AS delivered_at,
    4 AS tracking_event_count,
    NULL AS tracking_events,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'S2',
    'O2',
    NULL,
    'WINGBEAT',
    'EXPRESS',
    NULL,
    NULL,
    NULL,
    0,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'S3',
    'O3',
    'NEST',
    'FLAPWING',
    'Click & Collect',
    NULL,
    NULL,
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
    1 AS business_days_to_ship,
    NULL AS holidays_in_window,
    NULL AS dispatch_business_minutes,
    TRUE AS is_dispatch_on_time,
    NULL AS delivered_at_utc,
    26.0::DECIMAL(10, 2) AS hours_to_deliver
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
  UNION ALL
  SELECT
    'PK2',
    'S1',
    NULL,
    NULL,
    2.4::DECIMAL(10, 3),
    NULL,
    NULL,
    900,
    NULL,
    NULL
),

__ref__int_delivery_exceptions_classified AS (
  SELECT
    'X1' AS exception_id,
    'S1' AS shipment_id,
    NULL AS carrier_code,
    NULL AS exception_code,
    NULL AS responsibility,
    NULL AS occurred_at,
    NULL AS hours_to_resolve,
    NULL AS resolution_type,
    5.5::DECIMAL(18, 2) AS compensation_usd,
    NULL AS exception_rank_in_shipment
  UNION ALL
  SELECT
    'X2',
    'S1',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__expected__fct_shipments AS (
  SELECT
    'S1' AS shipment_id,
    'home_delivery' AS fulfilment_method,
    TRUE AS is_dispatch_on_time,
    26.0::NUMBER(10, 2) AS hours_to_deliver,
    2 AS package_count,
    3.9::DECIMAL(10, 3) AS chargeable_weight_kg,
    1500 AS rate_minor,
    2 AS exception_count,
    5.5::DECIMAL(18, 2) AS compensation_usd
  UNION ALL
  SELECT
    'S2' AS shipment_id,
    'partner' AS fulfilment_method,
    CAST(NULL AS BOOLEAN) AS is_dispatch_on_time,
    CAST(NULL AS NUMBER(10, 2)) AS hours_to_deliver,
    0 AS package_count,
    CAST(NULL AS DECIMAL(10, 3)) AS chargeable_weight_kg,
    CAST(NULL AS INT) AS rate_minor,
    0 AS exception_count,
    0.0::DECIMAL(18, 2) AS compensation_usd
  UNION ALL
  SELECT
    'S3' AS shipment_id,
    'click_and_collect' AS fulfilment_method,
    CAST(NULL AS BOOLEAN) AS is_dispatch_on_time,
    CAST(NULL AS NUMBER(10, 2)) AS hours_to_deliver,
    0 AS package_count,
    CAST(NULL AS DECIMAL(10, 3)) AS chargeable_weight_kg,
    CAST(NULL AS INT) AS rate_minor,
    0 AS exception_count,
    0.0::DECIMAL(18, 2) AS compensation_usd
),

__assert__shipment_id_is_unique_and_present AS (
  SELECT t.shipment_id
  FROM __ref("fct_shipments") AS t
  GROUP BY
    t.shipment_id
  HAVING
    COUNT(*) > 1
    OR t.shipment_id IS NULL
)
