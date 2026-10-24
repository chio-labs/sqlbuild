TEST (name "rpt_basket_mix_weekly__shares_units_by_category_within_each_week");

WITH __ref__fct_order_lines AS (
  SELECT
    'L1' AS order_line_id,
    'O1' AS order_id,
    NULL AS sku,
    NULL AS sku_family,
    'ducks' AS category_level_1,
    2 AS quantity,
    NULL AS unit_amount_minor,
    NULL AS list_amount_minor,
    NULL AS markdown_pct,
    NULL AS gross_amount_minor,
    100 AS discount_amount_minor,
    2000 AS net_amount_minor,
    NULL AS tax_amount_minor,
    NULL AS promo_codes,
    NULL AS has_stacked_promotions,
    NULL AS line_weight_kg
  UNION ALL
  SELECT
    'L2',
    'O1',
    NULL,
    NULL,
    'textiles',
    1,
    NULL,
    NULL,
    NULL,
    NULL,
    0,
    1500,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'L3',
    'O2',
    NULL,
    NULL,
    'ducks',
    3,
    NULL,
    NULL,
    NULL,
    NULL,
    0,
    3000,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'L4',
    'O3',
    NULL,
    NULL,
    NULL,
    1,
    NULL,
    NULL,
    NULL,
    NULL,
    0,
    500,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__fct_orders AS (
  SELECT
    'O1' AS order_id,
    NULL AS customer_id,
    NULL AS region_code,
    NULL AS placed_at,
    '2026-03-10'::DATE AS placed_date_local,
    NULL AS order_status,
    NULL AS sales_channel,
    NULL AS units,
    NULL AS currency_code,
    NULL AS amount,
    NULL AS amount_usd,
    NULL AS rate_to_usd,
    NULL AS rate_date,
    NULL AS gross_amount_usd,
    NULL AS discount_amount_usd,
    NULL AS tax_amount_usd,
    NULL AS promo_code,
    NULL AS utm_source,
    NULL AS utm_medium,
    NULL AS utm_campaign,
    NULL AS basket_size,
    NULL AS order_number,
    NULL AS is_first_order,
    NULL AS first_paid_at,
    NULL AS first_delivered_at,
    NULL AS hours_paid_to_shipped,
    NULL AS captured_minor,
    NULL AS refunded_minor,
    NULL AS net_collected_minor,
    NULL AS is_fully_refunded
  UNION ALL
  SELECT
    'O2',
    NULL,
    NULL,
    NULL,
    '2026-03-12'::DATE,
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
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'O3',
    NULL,
    NULL,
    NULL,
    '2026-03-16'::DATE,
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
    NULL,
    NULL,
    NULL
),

__expected__rpt_basket_mix_weekly AS (
  SELECT
    '2026-03-09:ducks' AS basket_week_key,
    2 AS order_count,
    5 AS units,
    5000 AS net_amount_minor,
    0.5::DECIMAL(9, 4) AS discounted_line_share,
    0.8333::DECIMAL(9, 4) AS unit_share_of_week,
    1 AS category_rank
  UNION ALL
  SELECT
    '2026-03-09:textiles' AS basket_week_key,
    1 AS order_count,
    1 AS units,
    1500 AS net_amount_minor,
    0.0::DECIMAL(9, 4) AS discounted_line_share,
    0.1667::DECIMAL(9, 4) AS unit_share_of_week,
    2 AS category_rank
  UNION ALL
  SELECT
    '2026-03-16:uncategorised' AS basket_week_key,
    1 AS order_count,
    1 AS units,
    500 AS net_amount_minor,
    0.0::DECIMAL(9, 4) AS discounted_line_share,
    1.0::DECIMAL(9, 4) AS unit_share_of_week,
    1 AS category_rank
),

__assert__basket_week_key_is_unique_and_present AS (
  SELECT t.basket_week_key
  FROM __ref("rpt_basket_mix_weekly") AS t
  GROUP BY
    t.basket_week_key
  HAVING
    COUNT(*) > 1
    OR t.basket_week_key IS NULL
)
