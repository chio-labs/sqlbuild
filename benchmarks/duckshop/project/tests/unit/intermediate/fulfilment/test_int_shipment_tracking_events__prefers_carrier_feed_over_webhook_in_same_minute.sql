TEST (name "int_shipment_tracking_events__prefers_carrier_feed_over_webhook_in_same_minute");

WITH __ref__stg_shipment_tracking_events AS (
  SELECT
    'E1' AS tracking_event_key,
    'S1' AS shipment_id,
    'carrier_api' AS event_source,
    'PICKED_UP' AS event_code,
    '2026-03-10 09:00:00 +01:00'::TIMESTAMP_TZ AS event_at,
    NULL AS location_text,
    NULL AS location_country_code,
    NULL AS event_sequence
  UNION ALL
  SELECT
    'E2',
    'S1',
    'carrier_api',
    'DELIVERED',
    '2026-03-11 14:00:30 +01:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'E3',
    'S1',
    'carrier_api',
    'IN_TRANSIT',
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'E4',
    'S1',
    'carrier_api',
    'OFD',
    '2026-03-11 08:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'E5',
    'S9',
    'carrier_api',
    'OFD',
    '2026-03-11 08:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL
),

__ref__int_carrier_webhook_events AS (
  SELECT
    'U1' AS carrier_update_key,
    'S1' AS shipment_id,
    NULL AS carrier_code,
    'DELIVERED' AS status_code,
    '2026-03-11 13:00:10 +00:00'::TIMESTAMP_TZ AS status_at,
    NULL AS received_at,
    NULL AS receive_lag_minutes,
    NULL AS is_batched
  UNION ALL
  SELECT
    'U2',
    'S1',
    NULL,
    'EXCEPTION_WEATHER',
    '2026-03-10 20:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL
),

__ref__stg_shipments AS (
  SELECT
    'S1' AS shipment_id,
    NULL AS order_id,
    'W1' AS warehouse_code,
    NULL AS carrier_code,
    NULL AS service_level,
    NULL AS tracking_number,
    NULL AS shipped_at,
    NULL AS delivered_at,
    NULL AS tracking_event_count,
    NULL AS tracking_events,
    NULL AS source_seq,
    NULL AS source_loaded_at
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

__expected__int_shipment_tracking_events AS (
  SELECT
    'E1' AS tracking_event_key,
    'collected' AS event_family,
    '2026-03-10 08:00:00'::TIMESTAMPNTZ AS event_at_utc,
    '2026-03-10 09:00:00'::TIMESTAMPNTZ AS event_at_warehouse_local,
    'carrier_api' AS event_origin,
    FALSE AS is_delivery_event
  UNION ALL
  SELECT
    'E2' AS tracking_event_key,
    'delivered' AS event_family,
    '2026-03-11 13:00:30'::TIMESTAMPNTZ AS event_at_utc,
    '2026-03-11 14:00:30'::TIMESTAMPNTZ AS event_at_warehouse_local,
    'carrier_api' AS event_origin,
    TRUE AS is_delivery_event
  UNION ALL
  SELECT
    'E4' AS tracking_event_key,
    'out_for_delivery' AS event_family,
    '2026-03-11 08:00:00'::TIMESTAMPNTZ AS event_at_utc,
    '2026-03-11 09:00:00'::TIMESTAMPNTZ AS event_at_warehouse_local,
    'carrier_api' AS event_origin,
    FALSE AS is_delivery_event
  UNION ALL
  SELECT
    'W:U2' AS tracking_event_key,
    'exception' AS event_family,
    '2026-03-10 20:00:00'::TIMESTAMPNTZ AS event_at_utc,
    '2026-03-10 21:00:00'::TIMESTAMPNTZ AS event_at_warehouse_local,
    'webhook' AS event_origin,
    FALSE AS is_delivery_event
)
