TEST (name "fct_order_lines__defaults_promotions_when_no_discounts_exist");

WITH __ref__int_order_lines_priced AS (
  SELECT
    'L1' AS order_line_id,
    'O1' AS order_id,
    'DUCK-MAL-01' AS sku,
    'DUCK' AS sku_family,
    NULL AS product_id,
    2 AS quantity,
    NULL AS unit_amount_minor,
    NULL AS list_amount_minor,
    NULL AS markdown_pct,
    NULL AS gross_amount_minor,
    2598 AS net_amount_minor,
    NULL AS discount_amount_minor,
    NULL AS tax_amount_minor,
    NULL AS line_weight_kg,
    NULL AS has_list_price
  UNION ALL
  SELECT
    'L2',
    'O1',
    'DECOY-TEAL-1',
    'DECOY',
    NULL,
    1,
    NULL,
    NULL,
    NULL,
    NULL,
    4500,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__int_order_lines_discounted AS (
  SELECT
    CAST(NULL AS VARCHAR) AS order_line_id,
    CAST(NULL AS VARCHAR) AS order_id,
    CAST(NULL AS VARCHAR) AS sku,
    CAST(NULL AS INT) AS quantity,
    CAST(NULL AS INT) AS gross_amount_minor,
    CAST(NULL AS INT) AS discount_amount_minor,
    CAST(NULL AS INT) AS net_amount_minor,
    CAST(NULL AS INT) AS tax_amount_minor,
    CAST(NULL AS OBJECT) AS discount_by_kind,
    CAST(NULL AS ARRAY) AS promo_codes,
    CAST(NULL AS BOOLEAN) AS has_stacked_promotions,
    CAST(NULL AS DECIMAL(9, 6)) AS discount_share
  WHERE 1 = 0
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
    NULL AS category_id,
    NULL AS category_slug_path,
    'ducks' AS category_level_1,
    NULL AS material,
    NULL AS weight_kg,
    NULL AS primary_image_url,
    NULL AS image_count,
    NULL AS is_active,
    NULL AS launched_on,
    NULL AS is_bundle_component
),

__expected__fct_order_lines AS (
  SELECT
    'L1' AS order_line_id,
    'ducks' AS category_level_1,
    2 AS quantity,
    2598 AS net_amount_minor,
    FALSE AS has_stacked_promotions
  UNION ALL
  SELECT
    'L2' AS order_line_id,
    CAST(NULL AS VARCHAR) AS category_level_1,
    1 AS quantity,
    4500 AS net_amount_minor,
    FALSE AS has_stacked_promotions
),

__assert__promo_codes_default_to_empty_arrays AS (
  SELECT l.order_line_id
  FROM __ref("fct_order_lines") AS l
  WHERE ARRAY_SIZE(l.promo_codes) <> 0
),

__assert__order_line_id_is_unique_and_present AS (
  SELECT t.order_line_id
  FROM __ref("fct_order_lines") AS t
  GROUP BY
    t.order_line_id
  HAVING
    COUNT(*) > 1
    OR t.order_line_id IS NULL
)
