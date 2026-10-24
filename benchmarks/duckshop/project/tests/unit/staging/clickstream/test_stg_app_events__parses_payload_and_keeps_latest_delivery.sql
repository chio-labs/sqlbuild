TEST (name "stg_app_events__parses_payload_and_keeps_latest_delivery");

WITH __source__clickstream__app_events AS (
  SELECT
    'a1' AS event_id,
    '2026-03-10 10:05:00'::TIMESTAMP_NTZ AS received_at,
    'Phone' AS platform,
    'v5.2.1 (build 9)' AS app_version,
    PARSE_JSON('{"name": "old"}')::VARIANT AS payload,
    '2026-03-10 11:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'a1',
    '2026-03-10 10:05:00'::TIMESTAMP_NTZ,
    'Phone',
    'v5.2.1 (build 9)',
    PARSE_JSON('{"name":"Screen_View","ts":"2026-03-10 10:04:59","device":{"id":"D1"},"user_id":null,"screen":"pdp"}')::VARIANT,
    '2026-03-10 12:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'a2',
    '2026-03-10 10:20:00'::TIMESTAMP_NTZ,
    'Tablet',
    '6',
    PARSE_JSON('{"name": "push_open", "ts_ms": 1773137400000, "device": {"id": "D2"}, "user_id": 42}')::VARIANT,
    '2026-03-10 12:00:00'::TIMESTAMP_NTZ
),

__expected__stg_app_events AS (
  SELECT
    'a1' AS event_id,
    'phone' AS platform,
    5 AS app_major_version,
    'screen_view' AS event_name,
    '2026-03-10 10:04:59'::TIMESTAMP_NTZ AS event_at_utc,
    'D1' AS device_id,
    CAST(NULL AS VARCHAR) AS customer_id,
    'pdp' AS screen_name
  UNION ALL
  SELECT
    'a2' AS event_id,
    'tablet' AS platform,
    6 AS app_major_version,
    'push_open' AS event_name,
    '2026-03-10 10:10:00'::TIMESTAMP_NTZ AS event_at_utc,
    'D2' AS device_id,
    '42' AS customer_id,
    CAST(NULL AS VARCHAR) AS screen_name
),

__assert__missing_attributes_become_empty_object AS (
  SELECT e.event_id
  FROM __ref("stg_app_events") AS e
  WHERE
    e.event_id = 'a2'
    AND ARRAY_SIZE(OBJECT_KEYS(e.attributes)) <> 0
)
