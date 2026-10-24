TEST (name "stg_carrier_webhook_errors__captures_unparseable_bodies");

WITH __source__fulfilment__carrier_webhooks AS (
  SELECT
    'W1' AS webhook_id,
    'flapwing' AS carrier_code,
    '2026-03-10 10:30:00'::TIMESTAMP_NTZ AS received_at,
    '{"event": "x"' AS body,
    '2026-03-10 11:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'W2',
    'flapwing',
    '2026-03-10 10:30:00'::TIMESTAMP_NTZ,
    '{"ok": true}',
    '2026-03-10 11:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'W3',
    'flapwing',
    '2026-03-10 10:30:00'::TIMESTAMP_NTZ,
    'Error   502   Bad gateway',
    '2026-03-10 11:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'W4',
    'flapwing',
    '2026-03-10 10:30:00'::TIMESTAMP_NTZ,
    'broken',
    '2026-03-10 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'W4',
    'flapwing',
    '2026-03-10 10:30:00'::TIMESTAMP_NTZ,
    '{"ok": true}',
    '2026-03-10 11:00:00'::TIMESTAMP_NTZ
),

__expected__stg_carrier_webhook_errors AS (
  SELECT
    'W1' AS webhook_id,
    'FLAPWING' AS carrier_code,
    13 AS body_length,
    '{"event": "x"' AS body_prefix,
    TRUE AS looks_truncated
  UNION ALL
  SELECT
    'W3' AS webhook_id,
    'FLAPWING' AS carrier_code,
    25 AS body_length,
    'Error 502 Bad gateway' AS body_prefix,
    FALSE AS looks_truncated
)
