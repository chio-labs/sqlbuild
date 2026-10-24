TEST (name "int_stock_on_hand_daily__carries_balance_and_last_count_forward");

WITH __ref__int_inventory_ledger AS (
  SELECT
    'M:1' AS ledger_entry_key,
    'DUCK-1' AS sku,
    'W1' AS warehouse_code,
    NULL AS entry_source,
    NULL AS qty_delta,
    '2026-03-28 10:00:00'::TIMESTAMPNTZ AS occurred_at_utc,
    '2026-03-28'::DATE AS occurred_date_local,
    5 AS running_on_hand,
    NULL AS entry_sequence,
    NULL AS is_negative_balance
  UNION ALL
  SELECT
    'M:2',
    'DUCK-1',
    'W1',
    NULL,
    NULL,
    '2026-03-30 12:00:00'::TIMESTAMPNTZ,
    '2026-03-30'::DATE,
    0,
    NULL,
    NULL
),

__ref__stg_stock_counts AS (
  SELECT
    'C1' AS count_id,
    'DUCK-1' AS sku,
    'W1' AS warehouse_code,
    6 AS counted_qty,
    '2026-03-29 09:00:00'::TIMESTAMP_NTZ AS counted_at_local,
    NULL AS counter_id,
    NULL AS is_blind_count,
    NULL AS counter,
    NULL AS source_seq,
    NULL AS source_loaded_at
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

__expected__int_stock_on_hand_daily AS (
  SELECT
    'DUCK-1|W1|2026-03-28' AS stock_day_key,
    '2026-03-01'::DATE AS month_start,
    5 AS on_hand_qty,
    CAST(NULL AS INT) AS last_counted_qty,
    CAST(NULL AS INT) AS days_since_count,
    FALSE AS is_stocked_out
  UNION ALL
  SELECT
    'DUCK-1|W1|2026-03-29' AS stock_day_key,
    '2026-03-01'::DATE AS month_start,
    5 AS on_hand_qty,
    6 AS last_counted_qty,
    0 AS days_since_count,
    FALSE AS is_stocked_out
  UNION ALL
  SELECT
    'DUCK-1|W1|2026-03-30' AS stock_day_key,
    '2026-03-01'::DATE AS month_start,
    0 AS on_hand_qty,
    6 AS last_counted_qty,
    1 AS days_since_count,
    TRUE AS is_stocked_out
  UNION ALL
  SELECT
    'DUCK-1|W1|2026-03-31' AS stock_day_key,
    '2026-03-01'::DATE AS month_start,
    0 AS on_hand_qty,
    6 AS last_counted_qty,
    2 AS days_since_count,
    TRUE AS is_stocked_out
)
