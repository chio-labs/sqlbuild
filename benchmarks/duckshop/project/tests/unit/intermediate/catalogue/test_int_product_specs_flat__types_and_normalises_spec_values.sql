TEST (name "int_product_specs_flat__types_and_normalises_spec_values");

WITH __ref__stg_products AS (
  SELECT
    'P1' AS product_id,
    NULL AS title,
    NULL AS category_path,
    NULL AS category_level_1,
    NULL AS category_level_2,
    NULL AS category_leaf,
    NULL AS category_depth,
    NULL AS brand_code,
    NULL AS launched_on,
    NULL AS is_active,
    NULL AS spec_key_count,
    OBJECT_CONSTRUCT(
      'Material',
      'cedar',
      'Colour Family',
      'Natural',
      'dishwasher_safe',
      'true',
      'width',
      '25 cm',
      'height',
      12.5,
      'finish',
      'oiled'
    )::OBJECT AS specs,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'P2',
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
    OBJECT_CONSTRUCT()::OBJECT,
    NULL,
    NULL
),

__expected__int_product_specs_flat AS (
  SELECT
    'P1' AS product_id,
    'Cedar' AS material,
    'natural' AS colour_family,
    25.0::DECIMAL(10, 2) AS width_cm,
    12.5::DECIMAL(10, 2) AS height_cm,
    CAST(NULL AS INT) AS capacity_ml,
    TRUE AS is_dishwasher_safe,
    2 AS numeric_spec_count
  UNION ALL
  SELECT
    'P2' AS product_id,
    CAST(NULL AS VARCHAR) AS material,
    CAST(NULL AS VARCHAR) AS colour_family,
    CAST(NULL AS DECIMAL(10, 2)) AS width_cm,
    CAST(NULL AS DECIMAL(10, 2)) AS height_cm,
    CAST(NULL AS INT) AS capacity_ml,
    CAST(NULL AS BOOLEAN) AS is_dishwasher_safe,
    0 AS numeric_spec_count
),

__assert__unmapped_specs_are_kept AS (
  SELECT s.product_id
  FROM __ref("int_product_specs_flat") AS s
  WHERE
    s.product_id = 'P1'
    AND s.other_specs:finish::VARCHAR IS DISTINCT FROM 'oiled'
)
