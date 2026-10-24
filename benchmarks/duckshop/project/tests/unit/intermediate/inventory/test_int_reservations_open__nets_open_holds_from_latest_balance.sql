TEST (name "int_reservations_open__nets_open_holds_from_latest_balance");

WITH __ref__int_inventory_ledger AS (
  SELECT
    'M:1' AS ledger_entry_key,
    'DUCK-1' AS sku,
    'W1' AS warehouse_code,
    NULL AS entry_source,
    NULL AS qty_delta,
    NULL AS occurred_at_utc,
    NULL AS occurred_date_local,
    10 AS running_on_hand,
    1 AS entry_sequence,
    NULL AS is_negative_balance
  UNION ALL
  SELECT
    'M:2',
    'DUCK-1',
    'W1',
    NULL,
    NULL,
    NULL,
    NULL,
    7,
    2,
    NULL
),

__ref__stg_stock_reservations AS (
  SELECT
    'R1' AS reservation_id,
    NULL AS order_id,
    'DUCK-1' AS sku,
    'W1' AS warehouse_code,
    3 AS qty,
    '2026-03-02 00:00:00 +00:00'::TIMESTAMP_TZ AS reserved_at,
    NULL AS released_at,
    TRUE AS is_open,
    NULL AS allocation_rule,
    FALSE AS is_backorder,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'R2',
    NULL,
    'DUCK-1',
    'W1',
    2,
    '2026-03-01 00:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    TRUE,
    NULL,
    TRUE,
    NULL,
    NULL
  UNION ALL
  SELECT
    'R3',
    NULL,
    'DUCK-1',
    'W1',
    4,
    '2026-02-01 00:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    FALSE,
    NULL,
    FALSE,
    NULL,
    NULL
),

__expected__int_reservations_open AS (
  SELECT
    'DUCK-1|W1' AS stock_key,
    2 AS open_reservations,
    3 AS reserved_qty,
    2 AS backordered_qty,
    7 AS on_hand_qty,
    4 AS available_to_promise,
    '2026-03-01 00:00:00 +00:00'::TIMESTAMP_TZ AS oldest_reserved_at
)
