TEST (name "rpt_wishlist_conversion__groups_unknown_products_as_unbranded");

WITH __ref__int_wishlist_demand AS (
  SELECT
    'DUCK-EID-01' AS sku,
    6 AS wishlisting_customers,
    NULL AS public_wishlist_count,
    3 AS purchased_after_wishlist,
    NULL AS wishlist_conversion_rate,
    4.0::DECIMAL(10, 2) AS median_days_to_purchase,
    NULL AS first_added_at
  UNION ALL
  SELECT
    'DECOY-PIN-02',
    2,
    NULL,
    0,
    NULL,
    NULL,
    NULL
),

__ref__dim_products AS (
  SELECT
    'DUCK-OTHER' AS sku,
    NULL AS product_id,
    NULL AS sku_family,
    'Teal Twin Pack' AS title,
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
),

__expected__rpt_wishlist_conversion AS (
  SELECT
    'Unbranded' AS brand_name,
    2 AS wishlisted_skus,
    8 AS wishlisting_customers,
    3 AS purchased_after_wishlist,
    0.375::DECIMAL(9, 6) AS conversion_rate,
    4.0::DECIMAL(10, 2) AS median_days_to_purchase
)

TEST (name "rpt_wishlist_conversion__leaves_rate_empty_without_wishlisters");

WITH __ref__int_wishlist_demand AS (
  SELECT
    'DUCK-MER-03' AS sku,
    0 AS wishlisting_customers,
    NULL AS public_wishlist_count,
    0 AS purchased_after_wishlist,
    NULL AS wishlist_conversion_rate,
    NULL AS median_days_to_purchase,
    NULL AS first_added_at
),

__ref__dim_products AS (
  SELECT
    'DUCK-MER-03' AS sku,
    NULL AS product_id,
    NULL AS sku_family,
    'Merganser Mini Duck' AS title,
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
),

__expected__rpt_wishlist_conversion AS (
  SELECT
    'Mallard & Co.' AS brand_name,
    1 AS wishlisted_skus,
    CAST(NULL AS DECIMAL(9, 6)) AS conversion_rate
),

__assert__rates_stay_within_bounds AS (
  SELECT r.brand_name
  FROM __ref("rpt_wishlist_conversion") AS r
  WHERE
    r.conversion_rate < 0
    OR r.conversion_rate > 1
)
