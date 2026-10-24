TEST (name "rpt_margin_by_category__reports_margin_quartiles_per_category_and_currency");

WITH __ref__int_product_margin AS (
  SELECT
    'DUCK-1:EUR' AS sku_price_key,
    'DUCK-1' AS sku,
    'EUR' AS currency_code,
    NULL AS list_price,
    NULL AS unit_cost,
    NULL AS unit_margin,
    50.0::DECIMAL(9, 2) AS margin_pct,
    FALSE AS is_below_cost,
    'ducks' AS category_level_1
  UNION ALL
  SELECT
    'DUCK-2:EUR',
    'DUCK-2',
    'EUR',
    NULL,
    NULL,
    NULL,
    40.0::DECIMAL(9, 2),
    FALSE,
    'ducks'
  UNION ALL
  SELECT
    'DUCK-3:EUR',
    'DUCK-3',
    'EUR',
    NULL,
    NULL,
    NULL,
    30.0::DECIMAL(9, 2),
    FALSE,
    'ducks'
  UNION ALL
  SELECT
    'DUCK-4:EUR',
    'DUCK-4',
    'EUR',
    NULL,
    NULL,
    NULL,
    -10.0::DECIMAL(9, 2),
    TRUE,
    'ducks'
  UNION ALL
  SELECT
    'BATH-1:USD',
    'BATH-1',
    'USD',
    NULL,
    NULL,
    NULL,
    10.0::DECIMAL(9, 2),
    FALSE,
    NULL
),

__expected__rpt_margin_by_category AS (
  SELECT
    'ducks:EUR' AS margin_key,
    4 AS sku_count,
    27.5::DECIMAL(9, 2) AS average_margin_pct,
    20.0::DECIMAL(9, 2) AS p25_margin_pct,
    42.5::DECIMAL(9, 2) AS p75_margin_pct,
    1 AS below_cost_skus
  UNION ALL
  SELECT
    'uncategorised:USD' AS margin_key,
    1 AS sku_count,
    10.0::DECIMAL(9, 2) AS average_margin_pct,
    10.0::DECIMAL(9, 2) AS p25_margin_pct,
    10.0::DECIMAL(9, 2) AS p75_margin_pct,
    0 AS below_cost_skus
),

__assert__margin_key_is_unique_and_present AS (
  SELECT t.margin_key
  FROM __ref("rpt_margin_by_category") AS t
  GROUP BY
    t.margin_key
  HAVING
    COUNT(*) > 1
    OR t.margin_key IS NULL
)
