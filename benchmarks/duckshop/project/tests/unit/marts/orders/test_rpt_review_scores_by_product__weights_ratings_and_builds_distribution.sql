TEST (name "rpt_review_scores_by_product__weights_ratings_and_builds_distribution");

WITH __ref__int_reviews_moderated AS (
  SELECT
    'RV1' AS review_id,
    'DUCK-MAL-01' AS sku,
    'P1' AS product_id,
    NULL AS customer_id,
    5 AS rating,
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ AS submitted_at,
    TRUE AS is_verified_purchase,
    2 AS sentiment_score,
    1.0::DECIMAL(6, 3) AS review_weight,
    NULL AS rating_rank_in_product
  UNION ALL
  SELECT
    'RV2',
    'DUCK-MAL-01',
    'P1',
    NULL,
    4,
    '2026-03-05 10:00:00 +00:00'::TIMESTAMP_TZ,
    FALSE,
    1,
    0.5::DECIMAL(6, 3),
    NULL
  UNION ALL
  SELECT
    'RV3',
    'DUCK-MAL-01',
    'P1',
    NULL,
    5,
    '2026-03-03 10:00:00 +00:00'::TIMESTAMP_TZ,
    TRUE,
    -1,
    0.5::DECIMAL(6, 3),
    NULL
  UNION ALL
  SELECT
    'RV4',
    'DUCK-MAL-01',
    'P2',
    NULL,
    1,
    '2026-03-02 10:00:00 +00:00'::TIMESTAMP_TZ,
    FALSE,
    -2,
    0.0::DECIMAL(6, 3),
    NULL
),

__expected__rpt_review_scores_by_product AS (
  SELECT
    'P1' AS product_id,
    3 AS review_count,
    4.75::DECIMAL(4, 2) AS weighted_rating,
    0.6667::DECIMAL(9, 4) AS verified_share,
    2 AS net_sentiment,
    '2026-03-05 10:00:00 +00:00'::TIMESTAMP_TZ AS latest_review_at
  UNION ALL
  SELECT
    'P2' AS product_id,
    1 AS review_count,
    CAST(NULL AS DECIMAL(4, 2)) AS weighted_rating,
    0.0::DECIMAL(9, 4) AS verified_share,
    -2 AS net_sentiment,
    '2026-03-02 10:00:00 +00:00'::TIMESTAMP_TZ AS latest_review_at
),

__assert__distribution_counts_each_rating AS (
  SELECT r.product_id
  FROM __ref("rpt_review_scores_by_product") AS r
  WHERE
    r.product_id = 'P1'
    AND (
      r.rating_distribution:"5"::INT <> 2
      OR r.rating_distribution:"4"::INT <> 1
    )
),

__assert__product_id_is_unique_and_present AS (
  SELECT t.product_id
  FROM __ref("rpt_review_scores_by_product") AS t
  GROUP BY
    t.product_id
  HAVING
    COUNT(*) > 1
    OR t.product_id IS NULL
)
