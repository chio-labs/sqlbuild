TEST (name "rpt_search_terms_top__ranks_terms_and_flags_merchandising_gaps");

WITH __ref__int_search_conversion AS (
  SELECT
    'rubber duck' AS search_term,
    50 AS search_count,
    25 AS searching_visitors,
    0.05::DECIMAL(9, 4) AS zero_result_rate,
    0.4::DECIMAL(9, 4) AS view_after_search_rate,
    NULL AS avg_results,
    NULL AS top_filter_category,
    NULL AS first_searched_at_utc
  UNION ALL
  SELECT
    'golden duck',
    30,
    15,
    0.3::DECIMAL(9, 4),
    0.5::DECIMAL(9, 4),
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'decoy',
    30,
    15,
    0.0::DECIMAL(9, 4),
    0.05::DECIMAL(9, 4),
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'pond pump',
    10,
    5,
    0.2::DECIMAL(9, 4),
    0.1::DECIMAL(9, 4),
    NULL,
    NULL,
    NULL
),

__expected__rpt_search_terms_top AS (
  SELECT
    'rubber duck' AS search_term,
    1 AS search_rank,
    FALSE AS needs_merchandising
  UNION ALL
  SELECT
    'decoy' AS search_term,
    2 AS search_rank,
    TRUE AS needs_merchandising
  UNION ALL
  SELECT
    'golden duck' AS search_term,
    3 AS search_rank,
    TRUE AS needs_merchandising
  UNION ALL
  SELECT
    'pond pump' AS search_term,
    4 AS search_rank,
    FALSE AS needs_merchandising
),

__assert__search_term_is_unique_and_present AS (
  SELECT t.search_term
  FROM __ref("rpt_search_terms_top") AS t
  GROUP BY
    t.search_term
  HAVING
    COUNT(*) > 1
    OR t.search_term IS NULL
)
