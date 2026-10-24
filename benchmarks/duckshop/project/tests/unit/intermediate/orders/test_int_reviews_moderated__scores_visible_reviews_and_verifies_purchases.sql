TEST (name "int_reviews_moderated__scores_visible_reviews_and_verifies_purchases");

WITH __ref__stg_reviews AS (
  SELECT
    'V1' AS review_id,
    'DUCK-1' AS sku,
    'C1' AS customer_id,
    5 AS rating,
    'Love it, great and sturdy' AS title,
    0 AS body_length,
    NULL AS submitted_at,
    'approved' AS moderation_status,
    ARRAY_CONSTRUCT()::ARRAY AS flagged_terms,
    NULL AS mentions_url,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'V2',
    'DUCK-1',
    'C2',
    2,
    'Broke after a week',
    0,
    NULL,
    'pending',
    ARRAY_CONSTRUCT()::ARRAY,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'V3',
    'DUCK-1',
    'C3',
    1,
    'spam',
    0,
    NULL,
    'approved',
    ARRAY_CONSTRUCT('link')::ARRAY,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'V4',
    'DUCK-1',
    'C4',
    4,
    'fine',
    0,
    NULL,
    'rejected',
    ARRAY_CONSTRUCT()::ARRAY,
    NULL,
    NULL,
    NULL
),

__ref__int_order_lines_priced AS (
  SELECT
    'L1' AS order_line_id,
    'O1' AS order_id,
    'DUCK-1' AS sku,
    NULL AS sku_family,
    'PR1' AS product_id,
    NULL AS quantity,
    NULL AS unit_amount_minor,
    NULL AS list_amount_minor,
    NULL AS markdown_pct,
    NULL AS gross_amount_minor,
    NULL AS net_amount_minor,
    NULL AS discount_amount_minor,
    NULL AS tax_amount_minor,
    NULL AS line_weight_kg,
    NULL AS has_list_price
),

__ref__stg_orders AS (
  SELECT
    'O1' AS order_id,
    'C1' AS customer_id,
    NULL AS storefront_code,
    NULL AS currency_code,
    NULL AS placed_at,
    NULL AS order_status,
    NULL AS sales_channel,
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

__ref__stg_product_variants AS (
  SELECT
    'DUCK-1' AS sku,
    'PR1' AS product_id,
    NULL AS colour,
    NULL AS size_label,
    NULL AS weight_grams,
    NULL AS weight_kg,
    NULL AS barcode_count,
    NULL AS is_fragile,
    NULL AS pack_size,
    NULL AS barcodes,
    NULL AS attributes,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__expected__int_reviews_moderated AS (
  SELECT
    'V1' AS review_id,
    'PR1' AS product_id,
    TRUE AS is_verified_purchase,
    3 AS sentiment_score,
    1.5::DECIMAL(6, 3) AS review_weight,
    1 AS rating_rank_in_product
  UNION ALL
  SELECT
    'V2' AS review_id,
    'PR1' AS product_id,
    FALSE AS is_verified_purchase,
    -1 AS sentiment_score,
    1.0::DECIMAL(6, 3) AS review_weight,
    2 AS rating_rank_in_product
)
