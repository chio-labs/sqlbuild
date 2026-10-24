TEST (name "stg_stock_movements__drops_voided_movements_and_splits_references");

WITH __source__inventory__stock_movements AS (
  SELECT
    'M1' AS movement_id,
    'duck-mal-01' AS sku,
    'pond' AS warehouse_code,
    20 AS qty_delta,
    'receipt' AS reason_code,
    'PO:PO1' AS reference,
    '2026-03-10 09:00:00'::TIMESTAMP_NTZ AS moved_at_local,
    PARSE_JSON('{}')::VARIANT AS metadata,
    '2026-03-10 11:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'M1',
    'duck-mal-01',
    'pond',
    24,
    'receipt',
    'PO:PO1',
    '2026-03-10 09:00:00'::TIMESTAMP_NTZ,
    PARSE_JSON('{"operator": "OP7"}')::VARIANT,
    '2026-03-10 12:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'M2',
    'duck-mal-01',
    'pond',
    -2,
    'damage',
    'ADJ:',
    '2026-03-10 09:00:00'::TIMESTAMP_NTZ,
    PARSE_JSON('{"operator": null}')::VARIANT,
    '2026-03-10 12:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'M3',
    'duck-mal-01',
    'pond',
    -5,
    'pick',
    'ORD:O1',
    '2026-03-10 09:00:00'::TIMESTAMP_NTZ,
    PARSE_JSON('{}')::VARIANT,
    '2026-03-10 12:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'M4',
    'duck-mal-01',
    'pond',
    5,
    'void',
    'VOID:M3',
    '2026-03-10 09:00:00'::TIMESTAMP_NTZ,
    PARSE_JSON('{}')::VARIANT,
    '2026-03-10 12:00:00'::TIMESTAMP_NTZ
),

__expected__stg_stock_movements AS (
  SELECT
    'M1' AS movement_id,
    'DUCK-MAL-01' AS sku,
    'POND' AS warehouse_code,
    24 AS qty_delta,
    'RECEIPT' AS reason_code,
    'PO' AS reference_type,
    'PO1' AS reference_id,
    'OP7' AS operator_id
  UNION ALL
  SELECT
    'M2' AS movement_id,
    'DUCK-MAL-01' AS sku,
    'POND' AS warehouse_code,
    -2 AS qty_delta,
    'DAMAGE' AS reason_code,
    'ADJ' AS reference_type,
    CAST(NULL AS VARCHAR) AS reference_id,
    CAST(NULL AS VARCHAR) AS operator_id
)
