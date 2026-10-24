TEST (name "stg_search_queries__cleans_query_text_and_reads_filters");

WITH __source__clickstream__search_queries AS (
  SELECT
    'Q1' AS query_id,
    'ANON1' AS anonymous_id,
    'red' AS query_text,
    1 AS results_count,
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ AS searched_at,
    NULL AS filters,
    '2026-03-10 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'Q1',
    'ANON1',
    '  Red  decoy!! 2L ',
    7,
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ,
    PARSE_JSON('{"category": "Decoys", "price": {"max_minor": 5000}, "sort": "price_asc"}')::VARIANT,
    '2026-03-10 11:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'Q2',
    'anon2',
    'towel',
    0,
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    '2026-03-10 11:00:00'::TIMESTAMP_NTZ
),

__expected__stg_search_queries AS (
  SELECT
    'Q1' AS query_id,
    'anon1' AS anonymous_id,
    'red  decoy   2l' AS query_text,
    3 AS query_token_count,
    7 AS results_count,
    'decoys' AS filter_category,
    5000 AS filter_max_price_minor,
    'price_asc' AS sort_order
  UNION ALL
  SELECT
    'Q2' AS query_id,
    'anon2' AS anonymous_id,
    'towel' AS query_text,
    1 AS query_token_count,
    0 AS results_count,
    CAST(NULL AS VARCHAR) AS filter_category,
    CAST(NULL AS INT) AS filter_max_price_minor,
    'relevance' AS sort_order
)
