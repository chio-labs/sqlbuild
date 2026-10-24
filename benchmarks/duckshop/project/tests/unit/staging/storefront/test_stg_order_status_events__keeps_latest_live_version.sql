TEST (name "stg_order_status_events__keeps_latest_live_version");

WITH __source__storefront__order_status_events AS (
  SELECT
    'K1' AS event_id,
    NULL AS order_id,
    NULL AS from_status,
    NULL AS to_status,
    NULL AS changed_at,
    NULL AS actor,
    'I' AS _op,
    1 AS _seq,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'K1',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'U',
    2,
    '2026-01-02 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'K2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'I',
    3,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'K2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'D',
    4,
    '2026-01-03 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_order_status_events AS (
  SELECT
    'K1' AS event_id,
    2 AS source_seq
)
