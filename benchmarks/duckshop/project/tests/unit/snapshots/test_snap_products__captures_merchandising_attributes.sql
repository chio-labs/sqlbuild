TEST (name "snap_products__captures_merchandising_attributes");

WITH __ref__stg_products AS (
  SELECT
    'P1' AS product_id,
    'Mallard Classic Duck' AS title,
    'ducks/rubber-ducks' AS category_path,
    NULL AS category_level_1,
    NULL AS category_level_2,
    NULL AS category_leaf,
    NULL AS category_depth,
    'MALLARD' AS brand_code,
    NULL AS launched_on,
    TRUE AS is_active,
    4 AS spec_key_count,
    NULL AS specs,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'P2',
    'Bill & Coo Duvet Cover',
    'textiles/bedding',
    NULL,
    NULL,
    NULL,
    NULL,
    'BILLCOO',
    NULL,
    FALSE,
    NULL,
    NULL,
    NULL,
    NULL
),

__expected__snap_products AS (
  SELECT
    'P1' AS product_id,
    'Mallard Classic Duck' AS title,
    'ducks/rubber-ducks' AS category_path,
    TRUE AS is_active,
    4 AS spec_key_count
  UNION ALL
  SELECT
    'P2' AS product_id,
    'Bill & Coo Duvet Cover' AS title,
    'textiles/bedding' AS category_path,
    FALSE AS is_active,
    CAST(NULL AS INT) AS spec_key_count
),

__assert__product_id_is_unique_and_present AS (
  SELECT t.product_id
  FROM __ref("snap_products") AS t
  GROUP BY
    t.product_id
  HAVING
    COUNT(*) > 1
    OR t.product_id IS NULL
)
