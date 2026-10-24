TEST (name "int_cart_abandonment__matches_orders_within_conversion_window");

WITH __ref__stg_carts AS (
  SELECT
    'K1' AS cart_id,
    'C1' AS customer_id,
    NULL AS anonymous_id,
    'DE' AS storefront_code,
    'active' AS cart_status,
    '2026-03-01 09:00:00 +00:00'::TIMESTAMP_TZ AS created_at,
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ AS updated_at,
    NULL AS line_count,
    NULL AS coupon_code,
    NULL AS contents,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'K2',
    'C2',
    NULL,
    'DE',
    'active',
    '2026-03-01 09:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'K3',
    'C3',
    NULL,
    'US',
    'merged',
    '2026-03-01 09:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_cart_items AS (
  SELECT
    'K1' AS cart_id,
    'K1#1' AS cart_item_key,
    'DUCK-A' AS sku,
    2 AS quantity,
    500 AS unit_amount_minor,
    NULL AS added_at
  UNION ALL
  SELECT
    'K1',
    'K1#2',
    'BED-B',
    NULL,
    1000,
    NULL
  UNION ALL
  SELECT
    'K2',
    'K2#1',
    'DUCK-C',
    1,
    300,
    NULL
  UNION ALL
  SELECT
    'K3',
    'K3#1',
    'DUCK-D',
    1,
    300,
    NULL
),

__ref__stg_orders AS (
  SELECT
    'O1' AS order_id,
    'C1' AS customer_id,
    NULL AS storefront_code,
    NULL AS currency_code,
    '2026-03-01 13:30:00 +00:00'::TIMESTAMP_TZ AS placed_at,
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
  UNION ALL
  SELECT
    'O0',
    'C1',
    NULL,
    NULL,
    '2026-03-03 13:30:00 +00:00'::TIMESTAMP_TZ,
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
    'O2',
    'C2',
    NULL,
    NULL,
    '2026-03-03 09:00:00 +00:00'::TIMESTAMP_TZ,
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

__expected__int_cart_abandonment AS (
  SELECT
    'K1' AS cart_id,
    2 AS item_count,
    3 AS units,
    2000 AS cart_value_minor,
    'O1' AS converted_order_id,
    TRUE AS is_converted,
    FALSE AS is_abandoned,
    3.5::DECIMAL(10, 2) AS hours_to_convert,
    2 AS distinct_sku_families
  UNION ALL
  SELECT
    'K2' AS cart_id,
    1 AS item_count,
    1 AS units,
    300 AS cart_value_minor,
    CAST(NULL AS VARCHAR) AS converted_order_id,
    FALSE AS is_converted,
    TRUE AS is_abandoned,
    CAST(NULL AS DECIMAL(10, 2)) AS hours_to_convert,
    1 AS distinct_sku_families
  UNION ALL
  SELECT
    'K3' AS cart_id,
    1 AS item_count,
    1 AS units,
    300 AS cart_value_minor,
    CAST(NULL AS VARCHAR) AS converted_order_id,
    FALSE AS is_converted,
    FALSE AS is_abandoned,
    CAST(NULL AS DECIMAL(10, 2)) AS hours_to_convert,
    1 AS distinct_sku_families
)
