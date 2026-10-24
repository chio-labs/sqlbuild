TEST (name "stg_po_receipts__keeps_latest_live_version");

WITH __source__inventory__po_receipts AS (
  SELECT
    'K1' AS receipt_id,
    NULL AS po_id,
    NULL AS sku,
    NULL AS warehouse_code,
    NULL AS received_qty,
    NULL AS damaged_qty,
    NULL AS received_at_local,
    NULL AS discrepancies,
    'I' AS _op,
    1 AS _seq,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'K1',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'U',
    2,
    '2026-01-02 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'K2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'I',
    3,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'K2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'D',
    4,
    '2026-01-03 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_po_receipts AS (
  SELECT
    'K1' AS receipt_id,
    2 AS source_seq
)
