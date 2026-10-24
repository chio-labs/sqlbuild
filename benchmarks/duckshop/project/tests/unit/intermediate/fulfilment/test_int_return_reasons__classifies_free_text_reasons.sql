TEST (name "int_return_reasons__classifies_free_text_reasons");

WITH __ref__stg_returns AS (
  SELECT
    'R1' AS return_id,
    'O1' AS order_id,
    'DUCK-1' AS sku,
    1 AS qty,
    'Arrived broken!!' AS reason_text,
    NULL AS return_status,
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ AS requested_at,
    NULL AS received_at,
    NULL AS photo_count,
    NULL AS refund_preference,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'R2',
    'O1',
    'DUCK-2',
    3,
    'Too small',
    NULL,
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'R3',
    'O1',
    'DUCK-3',
    1,
    NULL,
    NULL,
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'R4',
    'O2',
    'DUCK-1',
    1,
    'I don''t need it',
    NULL,
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'R5',
    'O1',
    'DUCK-1',
    1,
    'Wrong colour sent',
    NULL,
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_order_lines AS (
  SELECT
    'L1' AS order_line_id,
    'O1' AS order_id,
    NULL AS line_no,
    'DUCK-1' AS sku,
    2 AS quantity,
    NULL AS unit_amount_minor,
    NULL AS gross_amount_minor,
    NULL AS tax_amount_minor,
    NULL AS discount_count,
    NULL AS discounts,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'L2',
    'O1',
    NULL,
    'DUCK-2',
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
    'L3',
    'O1',
    NULL,
    'DUCK-2',
    1,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_orders AS (
  SELECT
    'O1' AS order_id,
    NULL AS customer_id,
    NULL AS storefront_code,
    NULL AS currency_code,
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ AS placed_at,
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
    NULL AS category_id,
    NULL AS category_slug_path,
    'decoys' AS category_level_1,
    NULL AS material,
    NULL AS weight_kg,
    NULL AS primary_image_url,
    NULL AS image_count,
    NULL AS is_active,
    NULL AS launched_on,
    NULL AS is_bundle_component
),

__expected__int_return_reasons AS (
  SELECT
    'R1' AS return_id,
    'damaged' AS return_reason,
    'pattern' AS classified_by,
    'decoys' AS category_level_1,
    2 AS ordered_qty,
    FALSE AS is_over_return,
    9 AS days_after_order
  UNION ALL
  SELECT
    'R2' AS return_id,
    'size_fit' AS return_reason,
    'pattern' AS classified_by,
    CAST(NULL AS VARCHAR) AS category_level_1,
    2 AS ordered_qty,
    TRUE AS is_over_return,
    9 AS days_after_order
  UNION ALL
  SELECT
    'R3' AS return_id,
    'other' AS return_reason,
    'default' AS classified_by,
    CAST(NULL AS VARCHAR) AS category_level_1,
    CAST(NULL AS INT) AS ordered_qty,
    TRUE AS is_over_return,
    9 AS days_after_order
  UNION ALL
  SELECT
    'R4' AS return_id,
    'changed_mind' AS return_reason,
    'pattern' AS classified_by,
    'decoys' AS category_level_1,
    CAST(NULL AS INT) AS ordered_qty,
    TRUE AS is_over_return,
    CAST(NULL AS INT) AS days_after_order
  UNION ALL
  SELECT
    'R5' AS return_id,
    'wrong_item' AS return_reason,
    'pattern' AS classified_by,
    'decoys' AS category_level_1,
    2 AS ordered_qty,
    FALSE AS is_over_return,
    9 AS days_after_order
)
