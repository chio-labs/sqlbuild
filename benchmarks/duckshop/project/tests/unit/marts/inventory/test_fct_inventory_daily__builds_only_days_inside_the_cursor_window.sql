TEST (name "fct_inventory_daily__builds_only_days_inside_the_cursor_window", cursor_start "2026-03-02", cursor_end "2026-03-03");

WITH __ref__int_stock_on_hand_daily AS (
  SELECT
    'DUCK-1|POND|2026-03-01' AS stock_day_key,
    'DUCK-1' AS sku,
    'POND' AS warehouse_code,
    '2026-03-01'::DATE AS calendar_date,
    NULL AS month_start,
    10 AS on_hand_qty,
    NULL AS last_counted_qty,
    NULL AS last_counted_date,
    5 AS days_since_count,
    FALSE AS is_stocked_out
  UNION ALL
  SELECT
    'DUCK-1|POND|2026-03-02',
    'DUCK-1',
    'POND',
    '2026-03-02'::DATE,
    NULL,
    -2,
    NULL,
    NULL,
    NULL,
    TRUE
  UNION ALL
  SELECT
    'DUCK-2|POND|2026-03-01',
    'DUCK-2',
    'POND',
    '2026-03-01'::DATE,
    NULL,
    4,
    NULL,
    NULL,
    100,
    FALSE
),

__ref__int_supplier_cost_current AS (
  SELECT
    'DUCK-1' AS sku,
    'SUP1' AS supplier_code,
    NULL AS supplier_name,
    NULL AS currency_code,
    NULL AS unit_cost_minor,
    2.5::DECIMAL(18, 4) AS unit_cost_usd,
    NULL AS effective_from,
    NULL AS supplier_count,
    NULL AS payment_terms_days,
    NULL AS cost_spread_pct
),

__expected__fct_inventory_daily AS (
  SELECT
    'DUCK-1|POND|2026-03-02' AS stock_day_key,
    -2 AS on_hand_qty
)
