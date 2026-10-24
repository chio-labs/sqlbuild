TEST (name "dim_products__enriches_sellable_skus_with_usd_margin_and_reviews");

WITH __ref__int_product_catalogue AS (
  SELECT
    'DUCK-MAL-01' AS sku,
    'P1' AS product_id,
    'DUCK' AS sku_family,
    'Mallard Classic Duck' AS title,
    NULL AS variant_label,
    NULL AS brand_code,
    'Mallard & Co.' AS brand_name,
    TRUE AS is_private_label,
    NULL AS category_id,
    NULL AS category_slug_path,
    'ducks' AS category_level_1,
    NULL AS material,
    NULL AS weight_kg,
    NULL AS primary_image_url,
    NULL AS image_count,
    TRUE AS is_active,
    NULL AS launched_on,
    NULL AS is_bundle_component
  UNION ALL
  SELECT
    'DUCK-TEAL-02',
    'P1',
    'DUCK',
    'Mallard Classic Duck',
    NULL,
    NULL,
    'Mallard & Co.',
    TRUE,
    NULL,
    NULL,
    'ducks',
    NULL,
    NULL,
    NULL,
    NULL,
    TRUE,
    NULL,
    NULL
  UNION ALL
  SELECT
    'BATH-EID-1',
    'P9',
    'BATH',
    'Eider Bath Set',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    TRUE,
    NULL,
    NULL
),

__ref__stg_products AS (
  SELECT
    'P1' AS product_id,
    'Mallard Classic Duck' AS title,
    NULL AS category_path,
    NULL AS category_level_1,
    NULL AS category_level_2,
    NULL AS category_leaf,
    NULL AS category_depth,
    NULL AS brand_code,
    NULL AS launched_on,
    NULL AS is_active,
    NULL AS spec_key_count,
    NULL AS specs,
    NULL AS source_seq,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ AS source_loaded_at
),

__ref__int_product_margin AS (
  SELECT
    'DUCK-MAL-01:USD' AS sku_price_key,
    'DUCK-MAL-01' AS sku,
    'USD' AS currency_code,
    12.99::DECIMAL(18, 4) AS list_price,
    NULL AS unit_cost,
    NULL AS unit_margin,
    55.0::DECIMAL(9, 2) AS margin_pct,
    NULL AS is_below_cost,
    NULL AS category_level_1
  UNION ALL
  SELECT
    'DUCK-MAL-01:EUR',
    'DUCK-MAL-01',
    'EUR',
    11.99::DECIMAL(18, 4),
    NULL,
    NULL,
    52.0::DECIMAL(9, 2),
    NULL,
    NULL
),

__ref__int_supplier_cost_current AS (
  SELECT
    'DUCK-MAL-01' AS sku,
    'SUP1' AS supplier_code,
    NULL AS supplier_name,
    NULL AS currency_code,
    NULL AS unit_cost_minor,
    NULL AS unit_cost_usd,
    NULL AS effective_from,
    2 AS supplier_count,
    NULL AS payment_terms_days,
    NULL AS cost_spread_pct
),

__ref__int_reviews_moderated AS (
  SELECT
    'RV1' AS review_id,
    'DUCK-MAL-01' AS sku,
    NULL AS product_id,
    NULL AS customer_id,
    5 AS rating,
    NULL AS submitted_at,
    NULL AS is_verified_purchase,
    NULL AS sentiment_score,
    NULL AS review_weight,
    NULL AS rating_rank_in_product
  UNION ALL
  SELECT
    'RV2',
    'DUCK-MAL-01',
    NULL,
    NULL,
    4,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'RV3',
    'DUCK-MAL-01',
    NULL,
    NULL,
    4,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__int_wishlist_demand AS (
  SELECT
    'DUCK-TEAL-02' AS sku,
    7 AS wishlisting_customers,
    NULL AS public_wishlist_count,
    NULL AS purchased_after_wishlist,
    NULL AS wishlist_conversion_rate,
    NULL AS median_days_to_purchase,
    NULL AS first_added_at
),

__expected__dim_products AS (
  SELECT
    'DUCK-MAL-01' AS sku,
    12.99::DECIMAL(18, 4) AS list_price_usd,
    55.0::DECIMAL(9, 2) AS margin_pct,
    'SUP1' AS primary_supplier_code,
    2 AS supplier_count,
    3 AS review_count,
    4.33::DECIMAL(4, 2) AS average_rating,
    0 AS wishlisting_customers
  UNION ALL
  SELECT
    'DUCK-TEAL-02' AS sku,
    CAST(NULL AS DECIMAL(18, 4)) AS list_price_usd,
    CAST(NULL AS DECIMAL(9, 2)) AS margin_pct,
    CAST(NULL AS VARCHAR) AS primary_supplier_code,
    0 AS supplier_count,
    0 AS review_count,
    CAST(NULL AS DECIMAL(4, 2)) AS average_rating,
    7 AS wishlisting_customers
),

__assert__sku_is_unique_and_present AS (
  SELECT t.sku
  FROM __ref("dim_products") AS t
  GROUP BY
    t.sku
  HAVING
    COUNT(*) > 1
    OR t.sku IS NULL
)
