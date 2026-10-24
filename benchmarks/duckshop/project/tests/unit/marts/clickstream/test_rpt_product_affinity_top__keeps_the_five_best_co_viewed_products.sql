TEST (name "rpt_product_affinity_top__keeps_the_five_best_co_viewed_products");

WITH __ref__int_product_view_affinity AS (
  SELECT
    'DUCK-1|DUCK-2' AS sku_pair_key,
    'DUCK-1' AS sku,
    'DUCK-2' AS co_viewed_sku,
    NULL AS co_viewers,
    20 AS sku_viewers,
    NULL AS co_view_rate,
    3.0::DECIMAL(12, 4) AS lift,
    1 AS pair_rank
  UNION ALL
  SELECT
    'DUCK-1|DUCK-3',
    'DUCK-1',
    'DUCK-3',
    NULL,
    20,
    NULL,
    2.5::DECIMAL(12, 4),
    2
  UNION ALL
  SELECT
    'DUCK-1|DUCK-4',
    'DUCK-1',
    'DUCK-4',
    NULL,
    20,
    NULL,
    2.0::DECIMAL(12, 4),
    3
  UNION ALL
  SELECT
    'DUCK-1|DUCK-5',
    'DUCK-1',
    'DUCK-5',
    NULL,
    20,
    NULL,
    1.5::DECIMAL(12, 4),
    4
  UNION ALL
  SELECT
    'DUCK-1|DUCK-6',
    'DUCK-1',
    'DUCK-6',
    NULL,
    20,
    NULL,
    1.2::DECIMAL(12, 4),
    5
  UNION ALL
  SELECT
    'DUCK-1|DUCK-7',
    'DUCK-1',
    'DUCK-7',
    NULL,
    20,
    NULL,
    9.0::DECIMAL(12, 4),
    6
  UNION ALL
  SELECT
    'DUCK-2|DUCK-1',
    'DUCK-2',
    'DUCK-1',
    NULL,
    8,
    NULL,
    1.1::DECIMAL(12, 4),
    1
),

__ref__dim_products AS (
  SELECT
    'DUCK-1' AS sku,
    NULL AS product_id,
    NULL AS sku_family,
    'Mallard Classic Duck' AS title,
    NULL AS variant_label,
    NULL AS brand_name,
    NULL AS is_private_label,
    NULL AS category_level_1,
    NULL AS category_slug_path,
    NULL AS is_active,
    NULL AS launched_on,
    NULL AS list_price_usd,
    NULL AS margin_pct,
    NULL AS primary_supplier_code,
    NULL AS supplier_count,
    NULL AS review_count,
    NULL AS average_rating,
    NULL AS wishlisting_customers,
    NULL AS source_loaded_at
),

__expected__rpt_product_affinity_top AS (
  SELECT
    'DUCK-1' AS sku,
    'Mallard Classic Duck' AS title,
    20 AS sku_viewers,
    3.0::DECIMAL(12, 4) AS best_lift
  UNION ALL
  SELECT
    'DUCK-2' AS sku,
    CAST(NULL AS VARCHAR) AS title,
    8 AS sku_viewers,
    1.1::DECIMAL(12, 4) AS best_lift
),

__assert__top_list_is_capped_and_ordered_by_rank AS (
  SELECT a.sku
  FROM __ref("rpt_product_affinity_top") AS a
  WHERE
    a.sku = 'DUCK-1'
    AND (
      ARRAY_SIZE(a.top_co_viewed) <> 5
      OR GET(a.top_co_viewed, 0):sku::VARCHAR <> 'DUCK-2'
    )
),

__assert__sku_is_unique_and_present AS (
  SELECT t.sku
  FROM __ref("rpt_product_affinity_top") AS t
  GROUP BY
    t.sku
  HAVING
    COUNT(*) > 1
    OR t.sku IS NULL
)
