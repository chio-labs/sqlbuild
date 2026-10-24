TEST (name "int_stock_count_variances__compares_counts_with_ledger_balance_at_count_time");

WITH __ref__int_inventory_ledger AS (
  SELECT
    'M:1' AS ledger_entry_key,
    'DUCK-1' AS sku,
    'W1' AS warehouse_code,
    NULL AS entry_source,
    NULL AS qty_delta,
    '2026-03-01 10:00:00'::TIMESTAMPNTZ AS occurred_at_utc,
    NULL AS occurred_date_local,
    100 AS running_on_hand,
    NULL AS entry_sequence,
    NULL AS is_negative_balance
  UNION ALL
  SELECT
    'M:2',
    'DUCK-1',
    'W1',
    NULL,
    NULL,
    '2026-03-05 10:00:00'::TIMESTAMPNTZ,
    NULL,
    90,
    NULL,
    NULL
),

__ref__stg_stock_counts AS (
  SELECT
    'C1' AS count_id,
    'DUCK-1' AS sku,
    'W1' AS warehouse_code,
    99 AS counted_qty,
    '2026-03-03 12:00:00'::TIMESTAMP_NTZ AS counted_at_local,
    NULL AS counter_id,
    TRUE AS is_blind_count,
    NULL AS counter,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'C2',
    'DUCK-1',
    'W1',
    80,
    '2026-03-06 08:00:00'::TIMESTAMP_NTZ,
    NULL,
    FALSE,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'C3',
    'DUCK-1',
    'W1',
    90,
    '2026-03-06 15:00:00'::TIMESTAMP_NTZ,
    NULL,
    FALSE,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'C4',
    'DUCK-1',
    'W1',
    5,
    '2026-03-01 09:00:00'::TIMESTAMP_NTZ,
    NULL,
    FALSE,
    NULL,
    NULL,
    NULL
),

__ref__stg_warehouses AS (
  SELECT
    'W1' AS warehouse_code,
    NULL AS warehouse_name,
    NULL AS country_code,
    'UTC' AS iana_timezone,
    NULL AS opens_local,
    NULL AS closes_local,
    NULL AS opening_minutes,
    NULL AS supports_same_day,
    NULL AS supports_cold_chain,
    NULL AS max_parcel_kg,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__expected__int_stock_count_variances AS (
  SELECT
    'C1' AS count_id,
    100 AS expected_qty,
    -1 AS variance_qty,
    -0.01::DECIMAL(9, 4) AS variance_pct,
    FALSE AS is_out_of_tolerance,
    1 AS recount_sequence
  UNION ALL
  SELECT
    'C2' AS count_id,
    90 AS expected_qty,
    -10 AS variance_qty,
    -0.1111::DECIMAL(9, 4) AS variance_pct,
    TRUE AS is_out_of_tolerance,
    1 AS recount_sequence
  UNION ALL
  SELECT
    'C3' AS count_id,
    90 AS expected_qty,
    0 AS variance_qty,
    0.0::DECIMAL(9, 4) AS variance_pct,
    FALSE AS is_out_of_tolerance,
    2 AS recount_sequence
  UNION ALL
  SELECT
    'C4' AS count_id,
    0 AS expected_qty,
    5 AS variance_qty,
    CAST(NULL AS DECIMAL(9, 4)) AS variance_pct,
    TRUE AS is_out_of_tolerance,
    1 AS recount_sequence
)
