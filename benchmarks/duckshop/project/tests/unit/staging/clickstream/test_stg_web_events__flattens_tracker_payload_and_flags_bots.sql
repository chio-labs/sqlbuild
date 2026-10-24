TEST (name "stg_web_events__flattens_tracker_payload_and_flags_bots");

WITH __source__clickstream__web_events AS (
  SELECT
    'w1' AS event_id,
    '2026-03-10 10:10:05'::TIMESTAMP_NTZ AS received_at,
    PARSE_JSON('{"type": "stale"}')::VARIANT AS event,
    '2026-03-10 10:11:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'w1',
    '2026-03-10 10:10:05'::TIMESTAMP_NTZ,
    OBJECT_CONSTRUCT_KEEP_NULL(
      'type',
      'Add To Cart',
      'ts_ms',
      1773137400000,
      'anonymous_id',
      'ANON1',
      'user',
      OBJECT_CONSTRUCT_KEEP_NULL('id', NULL, 'email', 'A+x@Example.com'),
      'page',
      OBJECT_CONSTRUCT(
        'url',
        'https://shop.example.com/p/duck-1?ref=x',
        'referrer',
        'https://WWW.Search.example.com/q'
      ),
      'context',
      OBJECT_CONSTRUCT(
        'ua',
        'Browser/5.0',
        'locale',
        'de_DE',
        'tz',
        'Europe/Berlin'
      ),
      'items',
      ARRAY_CONSTRUCT(OBJECT_CONSTRUCT('sku', 'duck-1'))
    )::VARIANT,
    '2026-03-10 10:12:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'w2',
    '2026-03-10 10:11:05'::TIMESTAMP_NTZ,
    OBJECT_CONSTRUCT(
      'type',
      'page_view',
      'ts_ms',
      1773137460000,
      'anonymous_id',
      'anon2',
      'user',
      OBJECT_CONSTRUCT('id', 'C7'),
      'context',
      OBJECT_CONSTRUCT('ua', 'ExampleBot/2.1')
    )::VARIANT,
    '2026-03-10 10:12:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'w3',
    '2026-03-10 10:12:05'::TIMESTAMP_NTZ,
    OBJECT_CONSTRUCT('type', 'page_view', 'anonymous_id', 'anon3')::VARIANT,
    '2026-03-10 10:13:00'::TIMESTAMP_NTZ
),

__expected__stg_web_events AS (
  SELECT
    'w1' AS event_id,
    'add_to_cart' AS event_type,
    '2026-03-10 10:10:00'::TIMESTAMP_NTZ AS event_at_utc,
    'anon1' AS anonymous_id,
    CAST(NULL AS VARCHAR) AS customer_id,
    'a@example.com' AS user_email,
    '/p/duck-1' AS page_path,
    'www.search.example.com' AS referrer_host,
    'de-DE' AS locale,
    'Europe/Berlin' AS client_timezone,
    FALSE AS is_bot
  UNION ALL
  SELECT
    'w2' AS event_id,
    'page_view' AS event_type,
    '2026-03-10 10:11:00'::TIMESTAMP_NTZ AS event_at_utc,
    'anon2' AS anonymous_id,
    'C7' AS customer_id,
    CAST(NULL AS VARCHAR) AS user_email,
    CAST(NULL AS VARCHAR) AS page_path,
    CAST(NULL AS VARCHAR) AS referrer_host,
    CAST(NULL AS VARCHAR) AS locale,
    CAST(NULL AS VARCHAR) AS client_timezone,
    TRUE AS is_bot
  UNION ALL
  SELECT
    'w3' AS event_id,
    'page_view' AS event_type,
    '2026-03-10 10:12:05'::TIMESTAMP_NTZ AS event_at_utc,
    'anon3' AS anonymous_id,
    CAST(NULL AS VARCHAR) AS customer_id,
    CAST(NULL AS VARCHAR) AS user_email,
    CAST(NULL AS VARCHAR) AS page_path,
    CAST(NULL AS VARCHAR) AS referrer_host,
    CAST(NULL AS VARCHAR) AS locale,
    CAST(NULL AS VARCHAR) AS client_timezone,
    FALSE AS is_bot
),

__assert__missing_items_become_empty_arrays AS (
  SELECT e.event_id
  FROM __ref("stg_web_events") AS e
  WHERE ARRAY_SIZE(e.items) <> IFF(e.event_id = 'w1', 1, 0)
)
