TEST (name "stg_product_variant_barcodes__drops_blank_and_shared_barcodes");

WITH __ref__stg_product_variants AS (
  SELECT
    'SKU1' AS sku,
    NULL AS product_id,
    NULL AS colour,
    NULL AS size_label,
    NULL AS weight_grams,
    NULL AS weight_kg,
    NULL AS barcode_count,
    NULL AS is_fragile,
    NULL AS pack_size,
    PARSE_JSON('["4006-3813-3393-1", "012345678905", ""]')::ARRAY AS barcodes,
    NULL AS attributes,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'SKU2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    PARSE_JSON('["012345678905", "96385074"]')::ARRAY,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'SKU3',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    PARSE_JSON('["12345", "12345"]')::ARRAY,
    NULL,
    NULL,
    NULL
),

__expected__stg_product_variant_barcodes AS (
  SELECT
    '4006381333931' AS barcode,
    'SKU1' AS sku,
    'EAN13' AS symbology,
    TRUE AS is_primary
  UNION ALL
  SELECT
    '96385074' AS barcode,
    'SKU2' AS sku,
    'EAN8' AS symbology,
    FALSE AS is_primary
  UNION ALL
  SELECT
    '12345' AS barcode,
    'SKU3' AS sku,
    'OTHER' AS symbology,
    TRUE AS is_primary
)
