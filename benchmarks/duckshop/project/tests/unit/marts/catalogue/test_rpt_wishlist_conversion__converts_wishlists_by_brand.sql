TEST (name "rpt_wishlist_conversion__converts_wishlists_by_brand");

WITH __ref__int_wishlist_demand AS (
  SELECT
    'DUCK-1' AS sku,
    10 AS wishlisting_customers,
    NULL AS public_wishlist_count,
    2 AS purchased_after_wishlist,
    NULL AS wishlist_conversion_rate,
    3.0::DECIMAL(10, 2) AS median_days_to_purchase,
    NULL AS first_added_at
  UNION ALL
  SELECT
    'DUCK-2',
    5,
    NULL,
    1,
    NULL,
    7.0::DECIMAL(10, 2),
    NULL
  UNION ALL
  SELECT
    'BATH-1',
    4,
    NULL,
    0,
    NULL,
    NULL,
    NULL
),

__ref__dim_products AS (
  SELECT
    'DUCK-1' AS sku,
    NULL AS product_id,
    NULL AS sku_family,
    NULL AS title,
    NULL AS variant_label,
    'Mallard & Co.' AS brand_name,
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
  UNION ALL
  SELECT
    'DUCK-2',
    NULL,
    NULL,
    NULL,
    NULL,
    'Mallard & Co.',
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
    NULL,
    NULL
),

__expected__rpt_wishlist_conversion AS (
  SELECT
    'Mallard & Co.' AS brand_name,
    2 AS wishlisted_skus,
    15 AS wishlisting_customers,
    3 AS purchased_after_wishlist,
    0.2::DECIMAL(9, 6) AS conversion_rate,
    5.0::DECIMAL(10, 2) AS median_days_to_purchase
  UNION ALL
  SELECT
    'Unbranded' AS brand_name,
    1 AS wishlisted_skus,
    4 AS wishlisting_customers,
    0 AS purchased_after_wishlist,
    0.0::DECIMAL(9, 6) AS conversion_rate,
    CAST(NULL AS DECIMAL(10, 2)) AS median_days_to_purchase
),

__assert__brand_name_is_unique_and_present AS (
  SELECT t.brand_name
  FROM __ref("rpt_wishlist_conversion") AS t
  GROUP BY
    t.brand_name
  HAVING
    COUNT(*) > 1
    OR t.brand_name IS NULL
)
