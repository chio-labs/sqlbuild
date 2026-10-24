TEST (name "rpt_category_tree_sales__rolls_sales_up_the_category_tree");

WITH __ref__int_category_paths AS (
  SELECT
    'C0' AS category_id,
    NULL AS parent_category_id,
    'ducks' AS slug,
    NULL AS display_name,
    'C0' AS root_category_id,
    1 AS depth,
    'ducks' AS slug_path,
    FALSE AS is_leaf,
    NULL AS sibling_rank
  UNION ALL
  SELECT
    'C1',
    'C0',
    'rubber-ducks',
    NULL,
    'C0',
    2,
    'ducks/rubber-ducks',
    FALSE,
    NULL
  UNION ALL
  SELECT
    'C2',
    'C1',
    'collectible',
    NULL,
    'C0',
    3,
    'ducks/rubber-ducks/collectible',
    TRUE,
    NULL
  UNION ALL
  SELECT
    'C3',
    'C0',
    'decoys',
    NULL,
    'C0',
    2,
    'ducks/decoys',
    TRUE,
    NULL
  UNION ALL
  SELECT
    'C4',
    NULL,
    'textiles',
    NULL,
    'C0',
    1,
    'textiles',
    TRUE,
    NULL
),

__ref__dim_products AS (
  SELECT
    'DUCK-1' AS sku,
    NULL AS product_id,
    NULL AS sku_family,
    NULL AS title,
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
  UNION ALL
  SELECT
    'DUCK-2',
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
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'DECOY-1',
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
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__int_product_catalogue AS (
  SELECT
    'DUCK-1' AS sku,
    NULL AS product_id,
    NULL AS sku_family,
    NULL AS title,
    NULL AS variant_label,
    NULL AS brand_code,
    NULL AS brand_name,
    NULL AS is_private_label,
    'C1' AS category_id,
    NULL AS category_slug_path,
    NULL AS category_level_1,
    NULL AS material,
    NULL AS weight_kg,
    NULL AS primary_image_url,
    NULL AS image_count,
    NULL AS is_active,
    NULL AS launched_on,
    NULL AS is_bundle_component
  UNION ALL
  SELECT
    'DUCK-2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'C2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'DECOY-1',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'C3',
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

__ref__fct_order_lines AS (
  SELECT
    'L1' AS order_line_id,
    'O1' AS order_id,
    'DUCK-1' AS sku,
    NULL AS sku_family,
    NULL AS category_level_1,
    2 AS quantity,
    NULL AS unit_amount_minor,
    NULL AS list_amount_minor,
    NULL AS markdown_pct,
    NULL AS gross_amount_minor,
    NULL AS discount_amount_minor,
    2000 AS net_amount_minor,
    NULL AS tax_amount_minor,
    NULL AS promo_codes,
    NULL AS has_stacked_promotions,
    NULL AS line_weight_kg
  UNION ALL
  SELECT
    'L2',
    'O1',
    'DUCK-2',
    NULL,
    NULL,
    3,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    4500,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'L3',
    'O2',
    'DECOY-1',
    NULL,
    NULL,
    5,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    10000,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'L4',
    'O3',
    'DUCK-1',
    NULL,
    NULL,
    1,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    1000,
    NULL,
    NULL,
    NULL,
    NULL
),

__expected__rpt_category_tree_sales AS (
  SELECT
    'C0' AS category_id,
    0 AS own_units,
    11 AS subtree_units,
    17500 AS subtree_net_amount_minor,
    CAST(NULL AS DECIMAL(9, 4)) AS share_of_parent_units
  UNION ALL
  SELECT
    'C1' AS category_id,
    3 AS own_units,
    6 AS subtree_units,
    7500 AS subtree_net_amount_minor,
    0.5455::DECIMAL(9, 4) AS share_of_parent_units
  UNION ALL
  SELECT
    'C2' AS category_id,
    3 AS own_units,
    3 AS subtree_units,
    4500 AS subtree_net_amount_minor,
    0.5::DECIMAL(9, 4) AS share_of_parent_units
  UNION ALL
  SELECT
    'C3' AS category_id,
    5 AS own_units,
    5 AS subtree_units,
    10000 AS subtree_net_amount_minor,
    0.4545::DECIMAL(9, 4) AS share_of_parent_units
  UNION ALL
  SELECT
    'C4' AS category_id,
    0 AS own_units,
    0 AS subtree_units,
    0 AS subtree_net_amount_minor,
    CAST(NULL AS DECIMAL(9, 4)) AS share_of_parent_units
),

__assert__category_id_is_unique_and_present AS (
  SELECT t.category_id
  FROM __ref("rpt_category_tree_sales") AS t
  GROUP BY
    t.category_id
  HAVING
    COUNT(*) > 1
    OR t.category_id IS NULL
)
