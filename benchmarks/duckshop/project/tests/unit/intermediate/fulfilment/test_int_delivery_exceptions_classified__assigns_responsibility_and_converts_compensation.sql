TEST (name "int_delivery_exceptions_classified__assigns_responsibility_and_converts_compensation");

WITH __ref__stg_delivery_exceptions AS (
  SELECT
    'X1' AS exception_id,
    'S1' AS shipment_id,
    'ADDR_INVALID' AS exception_code,
    NULL AS exception_text,
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ AS occurred_at,
    NULL AS resolution_type,
    '2026-03-01 11:30:00 +00:00'::TIMESTAMP_TZ AS resolved_at,
    500 AS compensation_minor,
    NULL AS resolution,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'X2',
    'S1',
    'LOST_PARCEL',
    NULL,
    '2026-03-02 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'X3',
    'S2',
    'WRONG_ITEM',
    NULL,
    '2026-03-03 08:00:00 +09:00'::TIMESTAMP_TZ,
    NULL,
    '2026-03-03 10:15:00 +09:00'::TIMESTAMP_TZ,
    1000,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'X4',
    'S2',
    'WEATHER',
    NULL,
    '2026-03-04 08:00:00 +09:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    0,
    NULL,
    NULL,
    NULL
),

__ref__stg_shipments AS (
  SELECT
    'S1' AS shipment_id,
    'O1' AS order_id,
    NULL AS warehouse_code,
    'FLAPWING' AS carrier_code,
    NULL AS service_level,
    NULL AS tracking_number,
    NULL AS shipped_at,
    NULL AS delivered_at,
    NULL AS tracking_event_count,
    NULL AS tracking_events,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'S2',
    'O2',
    NULL,
    'WINGBEAT',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__int_orders_usd AS (
  SELECT
    'O1' AS order_id,
    NULL AS customer_id,
    NULL AS region_code,
    'EUR' AS currency_code,
    NULL AS placed_at,
    NULL AS placed_date_local,
    NULL AS order_status,
    NULL AS sales_channel,
    NULL AS units,
    NULL AS amount,
    NULL AS amount_usd,
    NULL AS gross_amount_usd,
    NULL AS discount_amount_usd,
    NULL AS tax_amount_usd,
    1.1::NUMBER(18, 8) AS rate_to_usd,
    NULL AS rate_date,
    NULL AS rate_age_days,
    NULL AS is_rate_stale,
    NULL AS promo_code,
    NULL AS utm_source,
    NULL AS utm_medium,
    NULL AS utm_campaign,
    NULL AS basket_size
  UNION ALL
  SELECT
    'O2',
    NULL,
    NULL,
    'JPY',
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
    0.0067::NUMBER(18, 8),
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__expected__int_delivery_exceptions_classified AS (
  SELECT
    'X1' AS exception_id,
    'FLAPWING' AS carrier_code,
    'customer' AS responsibility,
    1.5::DECIMAL(10, 2) AS hours_to_resolve,
    5.5::DECIMAL(18, 2) AS compensation_usd,
    1 AS exception_rank_in_shipment
  UNION ALL
  SELECT
    'X2' AS exception_id,
    'FLAPWING' AS carrier_code,
    'carrier' AS responsibility,
    CAST(NULL AS DECIMAL(10, 2)) AS hours_to_resolve,
    CAST(NULL AS DECIMAL(18, 2)) AS compensation_usd,
    2 AS exception_rank_in_shipment
  UNION ALL
  SELECT
    'X3' AS exception_id,
    'WINGBEAT' AS carrier_code,
    'warehouse' AS responsibility,
    2.25::DECIMAL(10, 2) AS hours_to_resolve,
    6.7::DECIMAL(18, 2) AS compensation_usd,
    1 AS exception_rank_in_shipment
  UNION ALL
  SELECT
    'X4' AS exception_id,
    'WINGBEAT' AS carrier_code,
    'unknown' AS responsibility,
    CAST(NULL AS DECIMAL(10, 2)) AS hours_to_resolve,
    0.0::DECIMAL(18, 2) AS compensation_usd,
    2 AS exception_rank_in_shipment
)
