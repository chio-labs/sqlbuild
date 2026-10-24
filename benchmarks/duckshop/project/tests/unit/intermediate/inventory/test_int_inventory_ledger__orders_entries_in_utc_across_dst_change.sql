TEST (name "int_inventory_ledger__orders_entries_in_utc_across_dst_change");

WITH __ref__stg_stock_movements AS (
  SELECT
    'M1' AS movement_id,
    'DUCK-1' AS sku,
    'W1' AS warehouse_code,
    10 AS qty_delta,
    NULL AS reason_code,
    '2026-03-29 03:30:00'::TIMESTAMPNTZ AS moved_at_local,
    'ADJ' AS reference_type,
    NULL AS reference_id,
    NULL AS operator_id
  UNION ALL
  SELECT
    'M2',
    'DUCK-1',
    'W1',
    -3,
    NULL,
    '2026-03-29 01:30:00'::TIMESTAMPNTZ,
    'ADJ',
    NULL,
    NULL
  UNION ALL
  SELECT
    'M3',
    'DUCK-1',
    'W1',
    50,
    NULL,
    '2026-03-29 05:00:00'::TIMESTAMPNTZ,
    'PO',
    NULL,
    NULL
),

__ref__stg_po_receipts AS (
  SELECT
    'R1' AS receipt_id,
    'PO1' AS po_id,
    'DUCK-1' AS sku,
    'W1' AS warehouse_code,
    NULL AS received_qty,
    NULL AS damaged_qty,
    5 AS sellable_qty,
    '2026-03-30 09:00:00'::TIMESTAMP_NTZ AS received_at_local,
    NULL AS discrepancy_codes,
    NULL AS has_discrepancy,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__ref__stg_stock_transfers AS (
  SELECT
    'T1' AS transfer_id,
    'DUCK-1' AS sku,
    'W1' AS from_warehouse_code,
    'W2' AS to_warehouse_code,
    2 AS qty,
    '2026-03-31 10:00:00 +00:00'::TIMESTAMP_TZ AS shipped_at,
    NULL AS arrived_at,
    NULL AS transit_hours,
    NULL AS haulier_reference,
    NULL AS tracking,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__ref__stg_warehouses AS (
  SELECT
    'W1' AS warehouse_code,
    NULL AS warehouse_name,
    NULL AS country_code,
    'Europe/Berlin' AS iana_timezone,
    NULL AS opens_local,
    NULL AS closes_local,
    NULL AS opening_minutes,
    NULL AS supports_same_day,
    NULL AS supports_cold_chain,
    NULL AS max_parcel_kg,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'W2',
    NULL,
    NULL,
    'Europe/London',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__expected__int_inventory_ledger AS (
  SELECT
    'M:M2' AS ledger_entry_key,
    '2026-03-29 00:30:00'::TIMESTAMPNTZ AS occurred_at_utc,
    -3 AS running_on_hand,
    1 AS entry_sequence,
    TRUE AS is_negative_balance
  UNION ALL
  SELECT
    'M:M1' AS ledger_entry_key,
    '2026-03-29 01:30:00'::TIMESTAMPNTZ AS occurred_at_utc,
    7 AS running_on_hand,
    2 AS entry_sequence,
    FALSE AS is_negative_balance
  UNION ALL
  SELECT
    'R:R1' AS ledger_entry_key,
    '2026-03-30 07:00:00'::TIMESTAMPNTZ AS occurred_at_utc,
    12 AS running_on_hand,
    3 AS entry_sequence,
    FALSE AS is_negative_balance
  UNION ALL
  SELECT
    'TO:T1' AS ledger_entry_key,
    '2026-03-31 10:00:00'::TIMESTAMPNTZ AS occurred_at_utc,
    10 AS running_on_hand,
    4 AS entry_sequence,
    FALSE AS is_negative_balance
)
