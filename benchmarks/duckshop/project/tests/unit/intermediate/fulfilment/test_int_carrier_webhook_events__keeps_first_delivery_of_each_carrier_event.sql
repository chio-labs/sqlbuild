TEST (name "int_carrier_webhook_events__keeps_first_delivery_of_each_carrier_event");

WITH __ref__stg_carrier_webhooks AS (
  SELECT
    'U1' AS carrier_update_key,
    NULL AS webhook_id,
    'FLAPWING' AS carrier_code,
    '2026-03-10 09:05:00'::TIMESTAMP_NTZ AS received_at,
    'T1' AS tracking_number,
    'DELIVERED' AS status_code,
    '2026-03-10 10:00:00 +01:00'::TIMESTAMP_TZ AS status_at,
    1::DECIMAL(38, 0) AS carrier_event_id,
    FALSE AS is_batched
  UNION ALL
  SELECT
    'U2',
    NULL,
    'FLAPWING',
    '2026-03-10 09:10:00'::TIMESTAMP_NTZ,
    'T1',
    'DELIVERED',
    '2026-03-10 10:00:00 +01:00'::TIMESTAMP_TZ,
    1::DECIMAL(38, 0),
    FALSE
  UNION ALL
  SELECT
    'U3',
    NULL,
    'FLAPWING',
    '2026-03-10 12:30:00'::TIMESTAMP_NTZ,
    'T1',
    'OFD',
    '2026-03-10 12:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    TRUE
  UNION ALL
  SELECT
    'U4',
    NULL,
    'FLAPWING',
    '2026-03-10 12:30:00'::TIMESTAMP_NTZ,
    NULL,
    'OFD',
    '2026-03-10 12:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    FALSE
  UNION ALL
  SELECT
    'U5',
    NULL,
    'FLAPWING',
    '2026-03-10 12:30:00'::TIMESTAMP_NTZ,
    'T9',
    'OFD',
    '2026-03-10 12:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    FALSE
),

__ref__stg_shipments AS (
  SELECT
    'S1' AS shipment_id,
    NULL AS order_id,
    NULL AS warehouse_code,
    'FLAPWING' AS carrier_code,
    NULL AS service_level,
    'T1' AS tracking_number,
    NULL AS shipped_at,
    NULL AS delivered_at,
    NULL AS tracking_event_count,
    NULL AS tracking_events,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__expected__int_carrier_webhook_events AS (
  SELECT
    'U1' AS carrier_update_key,
    'S1' AS shipment_id,
    5 AS receive_lag_minutes,
    FALSE AS is_batched
  UNION ALL
  SELECT
    'U3' AS carrier_update_key,
    'S1' AS shipment_id,
    30 AS receive_lag_minutes,
    TRUE AS is_batched
)
