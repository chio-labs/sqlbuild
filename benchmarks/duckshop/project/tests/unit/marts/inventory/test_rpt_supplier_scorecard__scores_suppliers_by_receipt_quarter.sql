TEST (name "rpt_supplier_scorecard__scores_suppliers_by_receipt_quarter");

WITH __ref__int_purchase_order_lines_received AS (
  SELECT
    'PO1#1' AS po_line_key,
    'PO1' AS po_id,
    'SUP1' AS supplier_code,
    NULL AS warehouse_code,
    NULL AS sku,
    10 AS ordered_qty,
    12 AS received_qty,
    1 AS damaged_qty,
    NULL AS outstanding_qty,
    NULL AS fill_rate,
    '2026-03-12 10:00:00'::TIMESTAMP_NTZ AS first_received_at_local,
    1 AS days_late,
    NULL AS receipt_count,
    ARRAY_CONSTRUCT('SHORT')::ARRAY AS discrepancy_codes
  UNION ALL
  SELECT
    'PO1#2',
    'PO1',
    'SUP1',
    NULL,
    NULL,
    5,
    3,
    0,
    NULL,
    NULL,
    '2026-02-01 10:00:00'::TIMESTAMP_NTZ,
    0,
    NULL,
    ARRAY_CONSTRUCT('SHORT', 'DAMAGED')::ARRAY
  UNION ALL
  SELECT
    'PO1#3',
    'PO1',
    'SUP1',
    NULL,
    NULL,
    5,
    0,
    0,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    ARRAY_CONSTRUCT()::ARRAY
  UNION ALL
  SELECT
    'PO2#1',
    'PO1',
    'SUP1',
    NULL,
    NULL,
    10,
    10,
    0,
    NULL,
    NULL,
    '2026-04-02 10:00:00'::TIMESTAMP_NTZ,
    NULL,
    NULL,
    ARRAY_CONSTRUCT()::ARRAY
),

__expected__rpt_supplier_scorecard AS (
  SELECT
    'SUP1:2026-01-01' AS scorecard_key,
    2 AS po_lines,
    15 AS ordered_qty,
    15 AS received_qty,
    1.0::DECIMAL(9, 4) AS fill_rate,
    0.5::DECIMAL(9, 4) AS late_line_share,
    0.0667::DECIMAL(9, 4) AS damage_rate
  UNION ALL
  SELECT
    'SUP1:2026-04-01' AS scorecard_key,
    1 AS po_lines,
    10 AS ordered_qty,
    10 AS received_qty,
    1.0::DECIMAL(9, 4) AS fill_rate,
    0.0::DECIMAL(9, 4) AS late_line_share,
    0.0::DECIMAL(9, 4) AS damage_rate
),

__assert__discrepancy_codes_are_merged_without_duplicates AS (
  SELECT s.scorecard_key
  FROM __ref("rpt_supplier_scorecard") AS s
  WHERE
    ARRAY_SIZE(s.discrepancy_codes) <> IFF(s.scorecard_key = 'SUP1:2026-01-01', 2, 0)
    OR (
      s.scorecard_key = 'SUP1:2026-01-01'
      AND NOT ARRAY_CONTAINS('DAMAGED'::VARIANT, s.discrepancy_codes)
    )
),

__assert__scorecard_key_is_unique_and_present AS (
  SELECT t.scorecard_key
  FROM __ref("rpt_supplier_scorecard") AS t
  GROUP BY
    t.scorecard_key
  HAVING
    COUNT(*) > 1
    OR t.scorecard_key IS NULL
)
