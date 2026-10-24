TEST (name "int_search_conversion__measures_zero_results_and_views_after_search");

WITH __ref__stg_search_queries AS (
  SELECT
    'Q1' AS query_id,
    'V1' AS anonymous_id,
    'decoy' AS query_text,
    NULL AS query_token_count,
    5 AS results_count,
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ AS searched_at,
    'decoys' AS filter_category,
    NULL AS filter_max_price_minor,
    NULL AS sort_order,
    NULL AS filters
  UNION ALL
  SELECT
    'Q2',
    'V2',
    'decoy',
    NULL,
    0,
    '2026-03-10 11:00:00 +01:00'::TIMESTAMP_TZ,
    'decoys',
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'Q3',
    'V1',
    '',
    NULL,
    9,
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_web_searches AS (
  SELECT
    'W1' AS event_id,
    'V1' AS anonymous_id,
    '2026-03-10 09:00:00'::TIMESTAMP_NTZ AS searched_at_utc,
    'decoy' AS search_term,
    3 AS result_count,
    NULL AS is_zero_result
  UNION ALL
  SELECT
    'W2',
    'V3',
    '2026-03-10 12:00:00'::TIMESTAMP_NTZ,
    'towel',
    NULL,
    NULL
),

__ref__stg_web_product_views AS (
  SELECT
    'V1' AS anonymous_id,
    NULL AS customer_id,
    'V1:DUCK-1:2026-03-10 10:05:00' AS product_view_key,
    'DUCK-1' AS sku,
    '2026-03-10 10:05:00'::TIMESTAMPNTZ AS viewed_minute_utc,
    NULL AS list_name,
    NULL AS list_position
  UNION ALL
  SELECT
    'V2',
    NULL,
    'V2:DUCK-1:2026-03-10 10:20:00',
    'DUCK-1',
    '2026-03-10 10:20:00'::TIMESTAMPNTZ,
    NULL,
    NULL
  UNION ALL
  SELECT
    'V3',
    NULL,
    'V3:DUCK-2:2026-03-10 12:10:00',
    'DUCK-2',
    '2026-03-10 12:10:00'::TIMESTAMPNTZ,
    NULL,
    NULL
),

__expected__int_search_conversion AS (
  SELECT
    'decoy' AS search_term,
    3 AS search_count,
    2 AS searching_visitors,
    0.3333::DECIMAL(9, 4) AS zero_result_rate,
    0.3333::DECIMAL(9, 4) AS view_after_search_rate,
    2.67::DECIMAL(12, 2) AS avg_results,
    'decoys' AS top_filter_category,
    '2026-03-10 09:00:00'::TIMESTAMPNTZ AS first_searched_at_utc
  UNION ALL
  SELECT
    'towel' AS search_term,
    1 AS search_count,
    1 AS searching_visitors,
    1.0::DECIMAL(9, 4) AS zero_result_rate,
    1.0::DECIMAL(9, 4) AS view_after_search_rate,
    CAST(NULL AS DECIMAL(12, 2)) AS avg_results,
    CAST(NULL AS VARCHAR) AS top_filter_category,
    '2026-03-10 12:00:00'::TIMESTAMPNTZ AS first_searched_at_utc
)
