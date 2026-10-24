TEST (name "stg_product_variants__derives_weight_barcodes_and_handling_flags");

WITH __source__catalogue__product_variants AS (
  SELECT
    'duck 1_a' AS sku,
    'P1' AS product_id,
    ' navy blue ' AS colour,
    ' x l ' AS size_label,
    1250 AS weight_grams,
    PARSE_JSON('["4006381333931", " 0123 "]')::ARRAY AS barcodes,
    PARSE_JSON('{"handling": {"fragile": true}, "pack_size": "6"}')::VARIANT AS attributes,
    'I' AS _op,
    1 AS _seq,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'duck-2',
    'P2',
    'red',
    NULL,
    NULL,
    NULL,
    NULL,
    'I',
    3,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'duck-2',
    'P2',
    'dark red',
    NULL,
    NULL,
    NULL,
    NULL,
    'U',
    4,
    '2026-01-02 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_product_variants AS (
  SELECT
    'DUCK1-A' AS sku,
    'Navy Blue' AS colour,
    'XL' AS size_label,
    1.25::DECIMAL(10, 3) AS weight_kg,
    2 AS barcode_count,
    TRUE AS is_fragile,
    6 AS pack_size,
    1 AS source_seq
  UNION ALL
  SELECT
    'DUCK-2' AS sku,
    'Dark Red' AS colour,
    CAST(NULL AS VARCHAR) AS size_label,
    CAST(NULL AS DECIMAL(10, 3)) AS weight_kg,
    0 AS barcode_count,
    FALSE AS is_fragile,
    1 AS pack_size,
    4 AS source_seq
)
