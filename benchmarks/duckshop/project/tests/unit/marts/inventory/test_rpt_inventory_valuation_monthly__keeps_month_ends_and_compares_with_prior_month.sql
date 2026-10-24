TEST (name "rpt_inventory_valuation_monthly__keeps_month_ends_and_compares_with_prior_month");

WITH __ref__int_inventory_valuation_daily AS (
  SELECT
    'POND|2026-01-31' AS valuation_key,
    'POND' AS warehouse_code,
    '2026-01-31'::DATE AS calendar_date,
    NULL AS sku_count,
    100 AS units_on_hand,
    1000.0::DECIMAL(18, 2) AS stock_value_usd,
    0 AS unvalued_units,
    0 AS stocked_out_skus,
    NULL AS value_change_usd
  UNION ALL
  SELECT
    'POND|2026-02-15',
    'POND',
    '2026-02-15'::DATE,
    NULL,
    400,
    5000.0::DECIMAL(18, 2),
    0,
    0,
    NULL
  UNION ALL
  SELECT
    'POND|2026-02-28',
    'POND',
    '2026-02-28'::DATE,
    NULL,
    110,
    1200.0::DECIMAL(18, 2),
    0,
    0,
    NULL
  UNION ALL
  SELECT
    'POND|2026-03-31',
    'POND',
    '2026-03-31'::DATE,
    NULL,
    80,
    900.0::DECIMAL(18, 2),
    0,
    0,
    NULL
  UNION ALL
  SELECT
    'NEST|2026-03-31',
    'NEST',
    '2026-03-31'::DATE,
    NULL,
    40,
    500.0::DECIMAL(18, 2),
    0,
    0,
    NULL
),

__expected__rpt_inventory_valuation_monthly AS (
  SELECT
    'POND:2026-01-31' AS valuation_month_key,
    CAST(NULL AS DECIMAL(18, 2)) AS previous_month_value_usd,
    CAST(NULL AS DECIMAL(9, 2)) AS change_pct,
    100 AS units_on_hand
  UNION ALL
  SELECT
    'POND:2026-02-28' AS valuation_month_key,
    1000.0::DECIMAL(18, 2) AS previous_month_value_usd,
    20.0::DECIMAL(9, 2) AS change_pct,
    110 AS units_on_hand
  UNION ALL
  SELECT
    'POND:2026-03-31' AS valuation_month_key,
    1200.0::DECIMAL(18, 2) AS previous_month_value_usd,
    -25.0::DECIMAL(9, 2) AS change_pct,
    80 AS units_on_hand
  UNION ALL
  SELECT
    'NEST:2026-03-31' AS valuation_month_key,
    CAST(NULL AS DECIMAL(18, 2)) AS previous_month_value_usd,
    CAST(NULL AS DECIMAL(9, 2)) AS change_pct,
    40 AS units_on_hand
),

__assert__valuation_month_key_is_unique_and_present AS (
  SELECT t.valuation_month_key
  FROM __ref("rpt_inventory_valuation_monthly") AS t
  GROUP BY
    t.valuation_month_key
  HAVING
    COUNT(*) > 1
    OR t.valuation_month_key IS NULL
)
