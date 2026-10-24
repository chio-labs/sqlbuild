TEST (name "rpt_cart_abandonment_daily__counts_abandoned_value_by_utc_activity_day");

WITH __ref__int_cart_abandonment AS (
  SELECT
    'C1' AS cart_id,
    NULL AS customer_id,
    'eu-web' AS storefront_code,
    NULL AS cart_status,
    NULL AS item_count,
    NULL AS units,
    2500 AS cart_value_minor,
    '2026-03-10 23:30:00 -02:00'::TIMESTAMP_TZ AS last_activity_at,
    NULL AS converted_order_id,
    FALSE AS is_converted,
    TRUE AS is_abandoned,
    NULL AS hours_to_convert,
    NULL AS distinct_sku_families
  UNION ALL
  SELECT
    'C2',
    NULL,
    'eu-web',
    NULL,
    NULL,
    NULL,
    1000,
    '2026-03-11 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    TRUE,
    FALSE,
    2.5::DECIMAL(10, 2),
    NULL
  UNION ALL
  SELECT
    'C3',
    NULL,
    'eu-web',
    NULL,
    NULL,
    NULL,
    500,
    '2026-03-11 12:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    TRUE,
    FALSE,
    5.5::DECIMAL(10, 2),
    NULL
  UNION ALL
  SELECT
    'C4',
    NULL,
    'us-web',
    NULL,
    NULL,
    NULL,
    999,
    '2026-03-11 12:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    FALSE,
    FALSE,
    NULL,
    NULL
),

__expected__rpt_cart_abandonment_daily AS (
  SELECT
    'eu-web:2026-03-11' AS cart_day_key,
    3 AS carts,
    1 AS abandoned_carts,
    2 AS converted_carts,
    0.3333::DECIMAL(9, 4) AS abandonment_rate,
    2500 AS abandoned_value_minor,
    4.0::DECIMAL(10, 2) AS median_hours_to_convert
  UNION ALL
  SELECT
    'us-web:2026-03-11' AS cart_day_key,
    1 AS carts,
    0 AS abandoned_carts,
    0 AS converted_carts,
    0.0::DECIMAL(9, 4) AS abandonment_rate,
    0 AS abandoned_value_minor,
    CAST(NULL AS DECIMAL(10, 2)) AS median_hours_to_convert
),

__assert__cart_day_key_is_unique_and_present AS (
  SELECT t.cart_day_key
  FROM __ref("rpt_cart_abandonment_daily") AS t
  GROUP BY
    t.cart_day_key
  HAVING
    COUNT(*) > 1
    OR t.cart_day_key IS NULL
)
