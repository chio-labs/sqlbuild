TEST (name "int_inventory_valuation_daily__values_stock_and_tracks_daily_change");

WITH __ref__int_stock_on_hand_daily AS (
  SELECT
    'DUCK-1|W1|2026-03-01' AS stock_day_key,
    'DUCK-1' AS sku,
    'W1' AS warehouse_code,
    '2026-03-01'::DATE AS calendar_date,
    NULL AS month_start,
    10 AS on_hand_qty,
    NULL AS last_counted_qty,
    NULL AS last_counted_date,
    NULL AS days_since_count,
    FALSE AS is_stocked_out
  UNION ALL
  SELECT
    'DUCK-2|W1|2026-03-01',
    'DUCK-2',
    'W1',
    '2026-03-01'::DATE,
    NULL,
    -2,
    NULL,
    NULL,
    NULL,
    TRUE
  UNION ALL
  SELECT
    'DUCK-3|W1|2026-03-01',
    'DUCK-3',
    'W1',
    '2026-03-01'::DATE,
    NULL,
    4,
    NULL,
    NULL,
    NULL,
    FALSE
  UNION ALL
  SELECT
    'DUCK-1|W1|2026-03-02',
    'DUCK-1',
    'W1',
    '2026-03-02'::DATE,
    NULL,
    8,
    NULL,
    NULL,
    NULL,
    FALSE
),

__ref__int_supplier_cost_current AS (
  SELECT
    'DUCK-1' AS sku,
    NULL AS supplier_code,
    NULL AS supplier_name,
    NULL AS currency_code,
    NULL AS unit_cost_minor,
    2.5::DECIMAL(18, 4) AS unit_cost_usd,
    NULL AS effective_from,
    NULL AS supplier_count,
    NULL AS payment_terms_days,
    NULL AS cost_spread_pct
  UNION ALL
  SELECT
    'DUCK-2',
    NULL,
    NULL,
    NULL,
    NULL,
    1.0::DECIMAL(18, 4),
    NULL,
    NULL,
    NULL,
    NULL
),

__expected__int_inventory_valuation_daily AS (
  SELECT
    'W1|2026-03-01' AS valuation_key,
    3 AS sku_count,
    14 AS units_on_hand,
    25.0::DECIMAL(18, 2) AS stock_value_usd,
    4 AS unvalued_units,
    1 AS stocked_out_skus,
    CAST(NULL AS DECIMAL(18, 2)) AS value_change_usd
  UNION ALL
  SELECT
    'W1|2026-03-02' AS valuation_key,
    1 AS sku_count,
    8 AS units_on_hand,
    20.0::DECIMAL(18, 2) AS stock_value_usd,
    0 AS unvalued_units,
    0 AS stocked_out_skus,
    -5.0::DECIMAL(18, 2) AS value_change_usd
)
