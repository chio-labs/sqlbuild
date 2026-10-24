TEST (name "stg_app_events__reads_only_rows_received_in_the_cursor_window", cursor_start "2026-03-10 10:00:00", cursor_end "2026-03-10 11:00:00");

WITH __source__clickstream__app_events AS (
  SELECT
    'a0' AS event_id,
    '2026-03-10 09:59:59'::TIMESTAMP_NTZ AS received_at,
    'Phone' AS platform,
    '5' AS app_version,
    PARSE_JSON('{"name":"Screen_View","ts":"2026-03-10 10:04:59","device":{"id":"D1"},"user_id":null,"screen":"pdp"}')::VARIANT AS payload,
    '2026-03-10 12:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'a1',
    '2026-03-10 10:00:00'::TIMESTAMP_NTZ,
    'Phone',
    '5',
    PARSE_JSON('{"name":"Screen_View","ts":"2026-03-10 10:04:59","device":{"id":"D1"},"user_id":null,"screen":"pdp"}')::VARIANT,
    '2026-03-10 12:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'a2',
    '2026-03-10 11:00:00'::TIMESTAMP_NTZ,
    'Phone',
    '5',
    PARSE_JSON('{"name":"Screen_View","ts":"2026-03-10 10:04:59","device":{"id":"D1"},"user_id":null,"screen":"pdp"}')::VARIANT,
    '2026-03-10 12:00:00'::TIMESTAMP_NTZ
),

__expected__stg_app_events AS (
  SELECT
    'a1' AS event_id,
    '2026-03-10 10:00:00'::TIMESTAMP_NTZ AS received_at
)
