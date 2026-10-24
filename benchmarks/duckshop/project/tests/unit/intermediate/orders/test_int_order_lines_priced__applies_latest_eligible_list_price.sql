TEST (name "int_order_lines_priced__applies_latest_eligible_list_price");

WITH __ref__int_order_lines_discounted AS (
  SELECT
    'L1' AS order_line_id,
    'O1' AS order_id,
    'DUCK-KNF-08' AS sku,
    2 AS quantity,
    1600 AS gross_amount_minor,
    0 AS discount_amount_minor,
    1600 AS net_amount_minor,
    0 AS tax_amount_minor,
    NULL AS discount_by_kind,
    NULL AS promo_codes,
    NULL AS has_stacked_promotions,
    NULL AS discount_share
),

__ref__stg_order_lines AS (
  SELECT
    'L1' AS order_line_id,
    'O1' AS order_id,
    NULL AS line_no,
    'DUCK-KNF-08' AS sku,
    2 AS quantity,
    800 AS unit_amount_minor,
    NULL AS gross_amount_minor,
    NULL AS tax_amount_minor,
    NULL AS discount_count,
    NULL AS discounts,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__ref__stg_orders AS (
  SELECT
    'O1' AS order_id,
    NULL AS customer_id,
    NULL AS storefront_code,
    'EUR' AS currency_code,
    '2026-02-10 12:00:00 +01:00'::TIMESTAMP_TZ AS placed_at,
    NULL AS order_status,
    'web' AS sales_channel,
    NULL AS is_gift,
    NULL AS utm_source,
    NULL AS utm_medium,
    NULL AS utm_campaign,
    NULL AS device_type,
    NULL AS item_count_hint,
    NULL AS shipping_address_id,
    NULL AS attributes,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__ref__stg_price_lists AS (
  SELECT
    'P1' AS price_list_id,
    'DUCK-KNF-08' AS sku,
    'EUR' AS currency_code,
    900 AS list_amount_minor,
    '2026-01-01 00:00:00 +00:00'::TIMESTAMPTZ AS valid_from,
    NULL AS valid_to,
    NULL AS is_open_ended,
    1 AS min_quantity,
    ARRAY_CONSTRUCT()::ARRAY AS channel_restrictions,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'P2',
    'DUCK-KNF-08',
    'EUR',
    1000,
    '2026-02-01 00:00:00 +00:00'::TIMESTAMPTZ,
    NULL,
    NULL,
    1,
    ARRAY_CONSTRUCT()::ARRAY,
    NULL,
    NULL
  UNION ALL
  SELECT
    'P3',
    'DUCK-KNF-08',
    'EUR',
    700,
    '2026-02-05 00:00:00 +00:00'::TIMESTAMPTZ,
    NULL,
    NULL,
    1,
    ARRAY_CONSTRUCT('app')::ARRAY,
    NULL,
    NULL
  UNION ALL
  SELECT
    'P4',
    'DUCK-KNF-08',
    'EUR',
    600,
    '2026-02-06 00:00:00 +00:00'::TIMESTAMPTZ,
    NULL,
    NULL,
    10,
    ARRAY_CONSTRUCT()::ARRAY,
    NULL,
    NULL
),

__ref__stg_product_variants AS (
  SELECT
    'DUCK-KNF-08' AS sku,
    'PR1' AS product_id,
    NULL AS colour,
    NULL AS size_label,
    NULL AS weight_grams,
    0.25::DECIMAL(10, 3) AS weight_kg,
    NULL AS barcode_count,
    NULL AS is_fragile,
    NULL AS pack_size,
    NULL AS barcodes,
    NULL AS attributes,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__expected__int_order_lines_priced AS (
  SELECT
    'L1' AS order_line_id,
    'DUCK' AS sku_family,
    'PR1' AS product_id,
    1000 AS list_amount_minor,
    20.0::DECIMAL(9, 4) AS markdown_pct,
    0.5::DECIMAL(12, 3) AS line_weight_kg,
    TRUE AS has_list_price
)
