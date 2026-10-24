TEST (name "stg_web_searches__normalises_terms_and_flags_zero_results");

WITH __ref__stg_web_events AS (
  SELECT
    's1' AS event_id,
    NULL AS received_at,
    'search' AS event_type,
    '2026-03-10 10:00:00'::TIMESTAMP_NTZ AS event_at_utc,
    'v1' AS anonymous_id,
    NULL AS customer_id,
    NULL AS user_email,
    NULL AS page_url,
    NULL AS page_path,
    NULL AS referrer_host,
    NULL AS user_agent,
    NULL AS locale,
    NULL AS client_timezone,
    FALSE AS is_bot,
    PARSE_JSON('{"query": "  Red   Decoy ", "results": 12}')::OBJECT AS properties,
    PARSE_JSON('[]')::ARRAY AS items
  UNION ALL
  SELECT
    's2',
    NULL,
    'search',
    '2026-03-10 10:01:00'::TIMESTAMP_NTZ,
    'v1',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
    PARSE_JSON('{"query": "xyz", "results": 0}')::OBJECT,
    PARSE_JSON('[]')::ARRAY
  UNION ALL
  SELECT
    's3',
    NULL,
    'search',
    '2026-03-10 10:02:00'::TIMESTAMP_NTZ,
    'v1',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
    PARSE_JSON('{"query": "towel"}')::OBJECT,
    PARSE_JSON('[]')::ARRAY
  UNION ALL
  SELECT
    's4',
    NULL,
    'page_view',
    '2026-03-10 10:03:00'::TIMESTAMP_NTZ,
    'v1',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
    PARSE_JSON('{"query": "ignored"}')::OBJECT,
    PARSE_JSON('[]')::ARRAY
),

__expected__stg_web_searches AS (
  SELECT
    's1' AS event_id,
    'red decoy' AS search_term,
    12 AS result_count,
    FALSE AS is_zero_result
  UNION ALL
  SELECT
    's2' AS event_id,
    'xyz' AS search_term,
    0 AS result_count,
    TRUE AS is_zero_result
  UNION ALL
  SELECT
    's3' AS event_id,
    'towel' AS search_term,
    CAST(NULL AS INT) AS result_count,
    TRUE AS is_zero_result
)
