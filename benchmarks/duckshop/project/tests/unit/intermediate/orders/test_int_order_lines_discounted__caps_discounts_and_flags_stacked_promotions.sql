TEST (name "int_order_lines_discounted__caps_discounts_and_flags_stacked_promotions");

WITH __ref__stg_order_lines AS (
  SELECT
    'L1' AS order_line_id,
    'O1' AS order_id,
    NULL AS line_no,
    'DUCK-1' AS sku,
    2 AS quantity,
    NULL AS unit_amount_minor,
    1000 AS gross_amount_minor,
    200 AS tax_amount_minor,
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
    300,
    60,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'L3',
    'O2',
    NULL,
    'DUCK-3',
    1,
    NULL,
    500,
    100,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_order_line_discounts AS (
  SELECT
    'L1' AS order_line_id,
    'O1' AS order_id,
    'L1#0' AS order_line_discount_key,
    'SPRING' AS discount_code,
    'percent' AS discount_kind,
    100 AS discount_amount_minor
  UNION ALL
  SELECT
    'L1',
    'O1',
    'L1#1',
    'VIP',
    'fixed',
    50
  UNION ALL
  SELECT
    'L2',
    'O1',
    'L2#0',
    'BIG',
    'fixed',
    400
),

__ref__stg_promotions AS (
  SELECT
    'SPRING' AS promo_code,
    NULL AS promo_name,
    NULL AS starts_at,
    NULL AS ends_at,
    TRUE AS is_stackable,
    NULL AS rules,
    NULL AS min_order_minor,
    NULL AS eligible_regions,
    NULL AS tier_count,
    NULL AS max_discount_pct,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'VIP',
    NULL,
    NULL,
    NULL,
    TRUE,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'BIG',
    NULL,
    NULL,
    NULL,
    FALSE,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__expected__int_order_lines_discounted AS (
  SELECT
    'L1' AS order_line_id,
    150 AS discount_amount_minor,
    850 AS net_amount_minor,
    TRUE AS has_stacked_promotions,
    0.15::DECIMAL(9, 6) AS discount_share
  UNION ALL
  SELECT
    'L2' AS order_line_id,
    300 AS discount_amount_minor,
    0 AS net_amount_minor,
    FALSE AS has_stacked_promotions,
    1.333333::DECIMAL(9, 6) AS discount_share
  UNION ALL
  SELECT
    'L3' AS order_line_id,
    0 AS discount_amount_minor,
    500 AS net_amount_minor,
    FALSE AS has_stacked_promotions,
    0.0::DECIMAL(9, 6) AS discount_share
),

__assert__discount_by_kind_sums_to_discount AS (
  SELECT d.order_line_id
  FROM __ref("int_order_lines_discounted") AS d
  WHERE
    d.order_line_id = 'L1'
    AND (
      d.discount_by_kind:percent::INT <> 100
      OR d.discount_by_kind:fixed::INT <> 50
    )
)
