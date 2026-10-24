TEST (name "rpt_stock_count_accuracy__measures_monthly_count_accuracy");

WITH __ref__int_stock_count_variances AS (
  SELECT
    'C1' AS count_id,
    'DUCK-1' AS sku,
    'POND' AS warehouse_code,
    '2026-03-03 12:00:00'::TIMESTAMP_NTZ AS counted_at_local,
    NULL AS counted_qty,
    NULL AS expected_qty,
    0 AS variance_qty,
    NULL AS variance_pct,
    FALSE AS is_out_of_tolerance,
    TRUE AS is_blind_count,
    1 AS recount_sequence
  UNION ALL
  SELECT
    'C2',
    'DUCK-1',
    'POND',
    '2026-03-06 08:00:00'::TIMESTAMP_NTZ,
    NULL,
    NULL,
    -10,
    NULL,
    TRUE,
    FALSE,
    1
  UNION ALL
  SELECT
    'C3',
    'DUCK-1',
    'POND',
    '2026-03-06 15:00:00'::TIMESTAMP_NTZ,
    NULL,
    NULL,
    0,
    NULL,
    FALSE,
    FALSE,
    2
  UNION ALL
  SELECT
    'C4',
    'DUCK-1',
    'POND',
    '2026-04-01 09:00:00'::TIMESTAMP_NTZ,
    NULL,
    NULL,
    5,
    NULL,
    TRUE,
    TRUE,
    1
),

__expected__rpt_stock_count_accuracy AS (
  SELECT
    'POND:2026-03' AS count_month_key,
    3 AS counts,
    1 AS blind_counts,
    2 AS accurate_counts,
    0.6667::DECIMAL(9, 4) AS accuracy_rate,
    1 AS out_of_tolerance,
    -10 AS net_variance_qty,
    0.3333::DECIMAL(9, 4) AS recount_rate
  UNION ALL
  SELECT
    'POND:2026-04' AS count_month_key,
    1 AS counts,
    1 AS blind_counts,
    0 AS accurate_counts,
    0.0::DECIMAL(9, 4) AS accuracy_rate,
    1 AS out_of_tolerance,
    5 AS net_variance_qty,
    0.0::DECIMAL(9, 4) AS recount_rate
),

__assert__count_month_key_is_unique_and_present AS (
  SELECT t.count_month_key
  FROM __ref("rpt_stock_count_accuracy") AS t
  GROUP BY
    t.count_month_key
  HAVING
    COUNT(*) > 1
    OR t.count_month_key IS NULL
)
