TEST (name "int_product_catalogue__assembles_sellable_skus");

WITH __ref__stg_product_variants AS (
  SELECT
    'DUCK-MAL-08' AS sku,
    'P1' AS product_id,
    'Yellow' AS colour,
    '10cm' AS size_label,
    NULL AS weight_grams,
    0.3::DECIMAL(10, 3) AS weight_kg,
    NULL AS barcode_count,
    NULL AS is_fragile,
    NULL AS pack_size,
    NULL AS barcodes,
    NULL AS attributes,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'BED-X-1',
    'P2',
    'White',
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

__ref__stg_products AS (
  SELECT
    'P1' AS product_id,
    'Mallard Classic Duck' AS title,
    'ducks/decoys' AS category_path,
    'ducks' AS category_level_1,
    NULL AS category_level_2,
    NULL AS category_leaf,
    NULL AS category_depth,
    'B1' AS brand_code,
    NULL AS launched_on,
    TRUE AS is_active,
    NULL AS spec_key_count,
    NULL AS specs,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'P2',
    'Bill & Coo Duvet Cover',
    'textiles/bedding',
    'textiles',
    NULL,
    NULL,
    NULL,
    'B9',
    NULL,
    FALSE,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_brands AS (
  SELECT
    'B1' AS brand_code,
    'Mallard & Co.' AS brand_name,
    NULL AS country_code,
    TRUE AS is_private_label,
    NULL AS sustainability_rating,
    NULL AS founded_year,
    NULL AS brand_metadata,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__ref__int_category_paths AS (
  SELECT
    'C1' AS category_id,
    NULL AS parent_category_id,
    NULL AS slug,
    NULL AS display_name,
    NULL AS root_category_id,
    NULL AS depth,
    'ducks/decoys' AS slug_path,
    NULL AS is_leaf,
    NULL AS sibling_rank
),

__ref__stg_product_media AS (
  SELECT
    'M1' AS media_id,
    'P1' AS product_id,
    'https://cdn.test/2.jpg' AS media_url,
    'image' AS media_type,
    2 AS position,
    NULL AS width_px,
    NULL AS height_px,
    NULL AS aspect_ratio,
    NULL AS file_extension,
    NULL AS dimensions,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'M2',
    'P1',
    'https://cdn.test/1.jpg',
    'image',
    1,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'M3',
    'P1',
    'https://cdn.test/v.mp4',
    'video',
    0,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__int_product_specs_flat AS (
  SELECT
    'P1' AS product_id,
    'Vinyl' AS material,
    NULL AS colour_family,
    NULL AS width_cm,
    NULL AS height_cm,
    NULL AS capacity_ml,
    NULL AS is_dishwasher_safe,
    NULL AS spec_value_types,
    NULL AS other_specs,
    NULL AS numeric_spec_count
),

__ref__stg_bundle_components AS (
  SELECT
    'X1' AS component_id,
    'BNDL-1' AS bundle_sku,
    'DUCK-MAL-08' AS component_sku,
    NULL AS quantity,
    NULL AS is_optional,
    NULL AS substitute_skus,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__expected__int_product_catalogue AS (
  SELECT
    'DUCK-MAL-08' AS sku,
    'DUCK' AS sku_family,
    'Yellow / 10cm' AS variant_label,
    'Mallard & Co.' AS brand_name,
    TRUE AS is_private_label,
    'C1' AS category_id,
    'ducks/decoys' AS category_slug_path,
    'Vinyl' AS material,
    'https://cdn.test/1.jpg' AS primary_image_url,
    2 AS image_count,
    TRUE AS is_bundle_component
  UNION ALL
  SELECT
    'BED-X-1' AS sku,
    'BED' AS sku_family,
    CAST(NULL AS VARCHAR) AS variant_label,
    CAST(NULL AS VARCHAR) AS brand_name,
    FALSE AS is_private_label,
    CAST(NULL AS VARCHAR) AS category_id,
    'textiles/bedding' AS category_slug_path,
    CAST(NULL AS VARCHAR) AS material,
    CAST(NULL AS VARCHAR) AS primary_image_url,
    0 AS image_count,
    FALSE AS is_bundle_component
)
