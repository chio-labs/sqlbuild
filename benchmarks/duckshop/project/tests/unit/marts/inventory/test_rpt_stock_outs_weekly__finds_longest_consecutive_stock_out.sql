TEST (name "rpt_stock_outs_weekly__finds_longest_consecutive_stock_out");

WITH __ref__fct_inventory_daily AS (
  SELECT
    'DUCK-1|POND|2026-03-09' AS stock_day_key,
    'DUCK-1' AS sku,
    'POND' AS warehouse_code,
    '2026-03-09'::DATE AS calendar_date,
    5 AS on_hand_qty,
    NULL AS unit_cost_usd,
    NULL AS stock_value_usd,
    FALSE AS is_stocked_out,
    NULL AS days_since_count,
    FALSE AS is_count_overdue
  UNION ALL
  SELECT
    'DUCK-1|POND|2026-03-10',
    'DUCK-1',
    'POND',
    '2026-03-10'::DATE,
    0,
    NULL,
    NULL,
    TRUE,
    NULL,
    FALSE
  UNION ALL
  SELECT
    'DUCK-1|POND|2026-03-11',
    'DUCK-1',
    'POND',
    '2026-03-11'::DATE,
    0,
    NULL,
    NULL,
    TRUE,
    NULL,
    FALSE
  UNION ALL
  SELECT
    'DUCK-1|POND|2026-03-12',
    'DUCK-1',
    'POND',
    '2026-03-12'::DATE,
    5,
    NULL,
    NULL,
    FALSE,
    NULL,
    FALSE
  UNION ALL
  SELECT
    'DUCK-1|POND|2026-03-13',
    'DUCK-1',
    'POND',
    '2026-03-13'::DATE,
    0,
    NULL,
    NULL,
    TRUE,
    NULL,
    FALSE
  UNION ALL
  SELECT
    'DUCK-2|POND|2026-03-10',
    'DUCK-2',
    'POND',
    '2026-03-10'::DATE,
    5,
    NULL,
    NULL,
    FALSE,
    NULL,
    FALSE
  UNION ALL
  SELECT
    'DUCK-1|POND|2026-03-16',
    'DUCK-1',
    'POND',
    '2026-03-16'::DATE,
    0,
    NULL,
    NULL,
    TRUE,
    NULL,
    FALSE
),

__expected__rpt_stock_outs_weekly AS (
  SELECT
    'POND:2026-03-09' AS stock_out_key,
    6 AS sku_days,
    3 AS stocked_out_sku_days,
    0.5::DECIMAL(9, 4) AS stock_out_rate,
    1 AS skus_affected,
    2 AS longest_run_days
  UNION ALL
  SELECT
    'POND:2026-03-16' AS stock_out_key,
    1 AS sku_days,
    1 AS stocked_out_sku_days,
    1.0::DECIMAL(9, 4) AS stock_out_rate,
    1 AS skus_affected,
    1 AS longest_run_days
),

__assert__stock_out_key_is_unique_and_present AS (
  SELECT t.stock_out_key
  FROM __ref("rpt_stock_outs_weekly") AS t
  GROUP BY
    t.stock_out_key
  HAVING
    COUNT(*) > 1
    OR t.stock_out_key IS NULL
)
