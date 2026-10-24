TEST (name "stg_carrier_webhooks__splits_batched_updates_and_reads_both_payload_shapes");

WITH __source__fulfilment__carrier_webhooks AS (
  SELECT
    'H1' AS webhook_id,
    'flapwing' AS carrier_code,
    '2026-03-10 10:30:00'::TIMESTAMP_NTZ AS received_at,
    TO_JSON(OBJECT_CONSTRUCT(
      'tracking_number',
      'tr-001 23',
      'event_id',
      '77',
      'status',
      OBJECT_CONSTRUCT(
        'code',
        'delivered',
        'at',
        '2026-03-10 10:00:00 +01:00'
      )
    )) AS body,
    '2026-03-10 11:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'H2',
    'flapwing',
    '2026-03-10 10:30:00'::TIMESTAMP_NTZ,
    TO_JSON(OBJECT_CONSTRUCT(
      'events',
      ARRAY_CONSTRUCT(
        OBJECT_CONSTRUCT(
          'trackingNumber',
          'TR9',
          'event',
          'ofd',
          'timestamp',
          '2026-03-10 08:00:00 +00:00'
        ),
        OBJECT_CONSTRUCT(
          'trackingNumber',
          'TR9',
          'event',
          'pod',
          'event_id',
          'x1'
        )
      )
    )),
    '2026-03-10 11:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'H3',
    'flapwing',
    '2026-03-10 10:30:00'::TIMESTAMP_NTZ,
    'garbage',
    '2026-03-10 11:00:00'::TIMESTAMP_NTZ
),

__expected__stg_carrier_webhooks AS (
  SELECT
    'H1:0' AS carrier_update_key,
    'FLAPWING' AS carrier_code,
    'TR00123' AS tracking_number,
    'DELIVERED' AS status_code,
    '2026-03-10 10:00:00 +01:00'::TIMESTAMP_TZ AS status_at,
    77::DECIMAL(38, 0) AS carrier_event_id,
    FALSE AS is_batched
  UNION ALL
  SELECT
    'H2:0' AS carrier_update_key,
    'FLAPWING' AS carrier_code,
    'TR9' AS tracking_number,
    'OFD' AS status_code,
    '2026-03-10 08:00:00 +00:00'::TIMESTAMP_TZ AS status_at,
    CAST(NULL AS DECIMAL(38, 0)) AS carrier_event_id,
    TRUE AS is_batched
  UNION ALL
  SELECT
    'H2:1' AS carrier_update_key,
    'FLAPWING' AS carrier_code,
    'TR9' AS tracking_number,
    'POD' AS status_code,
    CAST(NULL AS TIMESTAMP_TZ) AS status_at,
    CAST(NULL AS DECIMAL(38, 0)) AS carrier_event_id,
    TRUE AS is_batched
)
