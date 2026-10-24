SCENARIO (
  description "Category paths built with CONNECT BY roll order-line sales up to every ancestor",
  tags ["catalogue", "category-tree"],
  expected_columns "all",
);

WITH __source__catalogue__categories AS (
  SELECT
    'C0' AS category_id,
    NULL AS parent_category_id,
    'Ducks' AS slug,
    'Ducks' AS display_name,
    1 AS sort_order,
    CAST(NULL AS VARIANT) AS translations,
    'I' AS _op,
    1 AS _seq,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'C1',
    'C0',
    'Rubber Ducks',
    'Rubber ducks',
    1,
    NULL,
    'I',
    2,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'C2',
    'C1',
    'collectible',
    'Collectible series',
    1,
    NULL,
    'I',
    3,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'C3',
    'C0',
    'decoys',
    'Decoys',
    2,
    NULL,
    'I',
    4,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'C4',
    'C4',
    'textiles',
    'Textiles',
    2,
    NULL,
    'I',
    5,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
),

__ref__dim_products AS (
  SELECT
    'DUCK-MAL-01' AS sku,
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
    'DUCK-PIN-02',
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
    'DECOY-TEAL-1',
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
    'DUCK-MAL-01' AS sku,
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
    'DUCK-PIN-02',
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
    'DECOY-TEAL-1',
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
    'DUCK-MAL-01' AS sku,
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
    'DUCK-PIN-02',
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
    'DECOY-TEAL-1',
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
    'DUCK-MAL-01',
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
    'ducks' AS slug_path,
    1 AS depth,
    FALSE AS is_leaf,
    0 AS own_units,
    11 AS subtree_units,
    17500 AS subtree_net_amount_minor,
    CAST(NULL AS DECIMAL(9, 4)) AS share_of_parent_units
  UNION ALL
  SELECT
    'C1' AS category_id,
    'ducks/rubber-ducks' AS slug_path,
    2 AS depth,
    FALSE AS is_leaf,
    3 AS own_units,
    6 AS subtree_units,
    7500 AS subtree_net_amount_minor,
    0.5455::DECIMAL(9, 4) AS share_of_parent_units
  UNION ALL
  SELECT
    'C2' AS category_id,
    'ducks/rubber-ducks/collectible' AS slug_path,
    3 AS depth,
    TRUE AS is_leaf,
    3 AS own_units,
    3 AS subtree_units,
    4500 AS subtree_net_amount_minor,
    0.5::DECIMAL(9, 4) AS share_of_parent_units
  UNION ALL
  SELECT
    'C3' AS category_id,
    'ducks/decoys' AS slug_path,
    2 AS depth,
    TRUE AS is_leaf,
    5 AS own_units,
    5 AS subtree_units,
    10000 AS subtree_net_amount_minor,
    0.4545::DECIMAL(9, 4) AS share_of_parent_units
  UNION ALL
  SELECT
    'C4' AS category_id,
    'textiles' AS slug_path,
    1 AS depth,
    TRUE AS is_leaf,
    0 AS own_units,
    0 AS subtree_units,
    0 AS subtree_net_amount_minor,
    CAST(NULL AS DECIMAL(9, 4)) AS share_of_parent_units
),

__assert__paths_start_at_a_root AS (
  SELECT p.category_id
  FROM __ref("int_category_paths") AS p
  WHERE
    p.root_category_id NOT IN ('C0', 'C4')
    OR (
      p.depth = 1
    ) <> (
      p.parent_category_id IS NULL
    )
)
