TEST (name "stg_purchase_orders__keeps_latest_live_version");

WITH __source__inventory__purchase_orders AS (
  SELECT
    'K1' AS po_id,
    NULL AS supplier_code,
    NULL AS warehouse_code,
    NULL AS currency_code,
    NULL AS po_status,
    NULL AS ordered_at,
    NULL AS expected_at,
    NULL AS received_at,
    NULL AS lines,
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
    NULL,
    'D',
    4,
    '2026-01-03 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_purchase_orders AS (
  SELECT
    'K1' AS po_id,
    2 AS source_seq
)
