TEST (name "int_fulfilment_sla__counts_business_days_across_easter_holidays");

WITH __ref__stg_shipments AS (
  SELECT
    'S1' AS shipment_id,
    'O1' AS order_id,
    'W1' AS warehouse_code,
    'FLAPWING' AS carrier_code,
    NULL AS service_level,
    NULL AS tracking_number,
    '2026-04-07 07:00:00 +00:00'::TIMESTAMP_TZ AS shipped_at,
    NULL AS delivered_at,
    NULL AS tracking_event_count,
    NULL AS tracking_events,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'S2',
    'O2',
    'W1',
    'FLAPWING',
    NULL,
    NULL,
    '2026-04-08 12:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'S3',
    'O3',
    'W1',
    'FLAPWING',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__int_orders_enriched AS (
  SELECT
    'O1' AS order_id,
    NULL AS customer_id,
    NULL AS storefront_code,
    NULL AS region_code,
    NULL AS storefront_timezone,
    NULL AS currency_code,
    '2026-04-03 08:00:00 +00:00'::TIMESTAMP_TZ AS placed_at,
    NULL AS placed_date_local,
    NULL AS order_status,
    NULL AS sales_channel,
    NULL AS line_count,
    NULL AS units,
    NULL AS gross_amount_minor,
    NULL AS discount_amount_minor,
    NULL AS net_amount_minor,
    NULL AS tax_amount_minor,
    NULL AS captured_amount_minor,
    NULL AS outstanding_amount_minor,
    NULL AS promo_code,
    NULL AS ship_to_country_code,
    NULL AS is_cross_border,
    NULL AS is_first_party_customer,
    NULL AS basket_size,
    NULL AS is_gift,
    NULL AS utm_source,
    NULL AS utm_medium,
    NULL AS utm_campaign,
    NULL AS total_weight_kg
  UNION ALL
  SELECT
    'O2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    '2026-04-08 06:00:00 +00:00'::TIMESTAMP_TZ,
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
  UNION ALL
  SELECT
    'O3',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    '2026-04-08 06:00:00 +00:00'::TIMESTAMP_TZ,
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

__ref__stg_warehouses AS (
  SELECT
    'W1' AS warehouse_code,
    NULL AS warehouse_name,
    'DE' AS country_code,
    'Europe/Berlin' AS iana_timezone,
    NULL AS opens_local,
    NULL AS closes_local,
    600 AS opening_minutes,
    NULL AS supports_same_day,
    NULL AS supports_cold_chain,
    NULL AS max_parcel_kg,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__ref__int_shipment_tracking_events AS (
  SELECT
    'E1' AS tracking_event_key,
    'S1' AS shipment_id,
    NULL AS event_code,
    NULL AS event_family,
    '2026-04-07 20:00:00'::TIMESTAMPNTZ AS event_at_utc,
    NULL AS event_at_warehouse_local,
    NULL AS event_origin,
    FALSE AS is_delivery_event
  UNION ALL
  SELECT
    'E2',
    'S1',
    NULL,
    NULL,
    '2026-04-08 09:00:00'::TIMESTAMPNTZ,
    NULL,
    NULL,
    TRUE
  UNION ALL
  SELECT
    'E3',
    'S1',
    NULL,
    NULL,
    '2026-04-09 09:00:00'::TIMESTAMPNTZ,
    NULL,
    NULL,
    TRUE
),

__seed__countries AS (
  SELECT
    'DE' AS country_code,
    NULL AS country_name,
    'EU' AS region_code,
    NULL AS default_timezone,
    NULL AS currency_code,
    NULL AS vat_registered
),

__seed__holiday_calendar AS (
  SELECT
    'EU' AS region_code,
    '2026-04-03'::DATE AS holiday_date,
    'Good Friday' AS holiday_name
  UNION ALL
  SELECT
    'EU',
    '2026-04-06'::DATE,
    'Easter Monday'
),

__expected__int_fulfilment_sla AS (
  SELECT
    'S1' AS shipment_id,
    '2026-04-03 10:00:00'::TIMESTAMPNTZ AS placed_at_local,
    '2026-04-07 09:00:00'::TIMESTAMPNTZ AS shipped_at_local,
    4 AS calendar_days_to_ship,
    1 AS business_days_to_ship,
    1 AS holidays_in_window,
    600 AS dispatch_business_minutes,
    FALSE AS is_dispatch_on_time,
    '2026-04-08 09:00:00'::TIMESTAMP_NTZ AS delivered_at_utc,
    26.0::DECIMAL(10, 2) AS hours_to_deliver
  UNION ALL
  SELECT
    'S2' AS shipment_id,
    '2026-04-08 08:00:00'::TIMESTAMPNTZ AS placed_at_local,
    '2026-04-08 14:00:00'::TIMESTAMPNTZ AS shipped_at_local,
    0 AS calendar_days_to_ship,
    0 AS business_days_to_ship,
    0 AS holidays_in_window,
    360 AS dispatch_business_minutes,
    TRUE AS is_dispatch_on_time,
    CAST(NULL AS TIMESTAMP_NTZ) AS delivered_at_utc,
    CAST(NULL AS DECIMAL(10, 2)) AS hours_to_deliver
)
