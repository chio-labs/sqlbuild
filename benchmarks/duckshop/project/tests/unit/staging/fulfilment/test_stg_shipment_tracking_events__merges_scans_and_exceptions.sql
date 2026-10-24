TEST (name "stg_shipment_tracking_events__merges_scans_and_exceptions");

WITH __ref__stg_shipments AS (
  SELECT
    'S1' AS shipment_id,
    NULL AS order_id,
    NULL AS warehouse_code,
    NULL AS carrier_code,
    NULL AS service_level,
    NULL AS tracking_number,
    NULL AS shipped_at,
    NULL AS delivered_at,
    NULL AS tracking_event_count,
    ARRAY_CONSTRUCT(
      OBJECT_CONSTRUCT(
        'code',
        'picked-up',
        'ts',
        '2026-03-10 09:00:00 +01:00',
        'location',
        'berlin hub, de'
      ),
      OBJECT_CONSTRUCT(
        'code',
        'OUT_FOR_DELIVERY',
        'ts',
        '11/03/2026 08:00 +0100',
        'location',
        'Munich'
      )
    )::ARRAY AS tracking_events,
    NULL AS source_seq,
    NULL AS source_loaded_at
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
    NULL,
    NULL
),

__ref__stg_delivery_exceptions AS (
  SELECT
    'X1' AS exception_id,
    'S1' AS shipment_id,
    'DAMAGED' AS exception_code,
    NULL AS exception_text,
    '2026-03-11 12:00:00 +00:00'::TIMESTAMP_TZ AS occurred_at,
    NULL AS resolution_type,
    NULL AS resolved_at,
    NULL AS compensation_minor,
    NULL AS resolution,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__expected__stg_shipment_tracking_events AS (
  SELECT
    'S1:0' AS tracking_event_key,
    'scan' AS event_source,
    'PICKEDUP' AS event_code,
    '2026-03-10 09:00:00 +01:00'::TIMESTAMP_TZ AS event_at,
    'Berlin Hub' AS location_text,
    'DE' AS location_country_code,
    0 AS event_sequence
  UNION ALL
  SELECT
    'S1:1' AS tracking_event_key,
    'scan' AS event_source,
    'OUT_FOR_DELIVERY' AS event_code,
    '2026-03-11 08:00:00 +01:00'::TIMESTAMP_TZ AS event_at,
    'Munich' AS location_text,
    CAST(NULL AS VARCHAR) AS location_country_code,
    1 AS event_sequence
  UNION ALL
  SELECT
    'S1:x:X1' AS tracking_event_key,
    'exception' AS event_source,
    'EXCEPTION_DAMAGED' AS event_code,
    '2026-03-11 12:00:00 +00:00'::TIMESTAMP_TZ AS event_at,
    CAST(NULL AS VARCHAR) AS location_text,
    CAST(NULL AS VARCHAR) AS location_country_code,
    CAST(NULL AS INT) AS event_sequence
)
