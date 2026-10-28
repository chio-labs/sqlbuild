TEST (name "rpt_edge_stock_reconciliation__keeps_rows_found_on_only_one_side");

WITH __ref__stg_edge_ledger_entries AS (
  SELECT
    v.entry_id,
    NULL AS order_ref,
    NULL AS channel,
    NULL AS line_no,
    v.sku,
    v.warehouse_code,
    v.quantity::NUMBER(38, 0) AS quantity,
    NULL AS quantity_text,
    NULL AS quantity_from_text,
    NULL AS quantity_text_decimal,
    NULL AS unit_price_minor,
    NULL AS amount,
    NULL AS currency_code,
    NULL AS fx_rate,
    v.status
  FROM VALUES
    ('LE-01', 'MALLARD-01', 'POND', 3, 'allocated'),
    ('LE-02', 'MALLARD-01', 'POND', 2, 'COUNTED'),
    ('LE-03', 'TEAL-02', 'POND', 4, 'Allocated'),
    ('LE-04', 'TEAL-02', 'NEST', 1, 'counted'),
    ('LE-05', 'EIDER-03', NULL, 5, 'allocated'),
    ('LE-06', 'EIDER-03', NULL, 5, 'counted'),
    ('LE-07', 'PINTAIL-04', 'MARSH', 9, 'pending') AS v(entry_id, sku, warehouse_code, quantity, status)
),

__expected__rpt_edge_stock_reconciliation AS (
  SELECT
    'EIDER-03' AS sku,
    CAST(NULL AS VARCHAR) AS warehouse_code,
    5 AS allocated_units,
    CAST(NULL AS NUMBER(38, 0)) AS counted_units,
    -5 AS variance_units
  UNION ALL
  SELECT
    'EIDER-03' AS sku,
    CAST(NULL AS VARCHAR) AS warehouse_code,
    CAST(NULL AS NUMBER(38, 0)) AS allocated_units,
    5 AS counted_units,
    5 AS variance_units
  UNION ALL
  SELECT
    'MALLARD-01' AS sku,
    'POND' AS warehouse_code,
    3 AS allocated_units,
    2 AS counted_units,
    -1 AS variance_units
  UNION ALL
  SELECT
    'TEAL-02' AS sku,
    'NEST' AS warehouse_code,
    CAST(NULL AS NUMBER(38, 0)) AS allocated_units,
    1 AS counted_units,
    1 AS variance_units
  UNION ALL
  SELECT
    'TEAL-02' AS sku,
    'POND' AS warehouse_code,
    4 AS allocated_units,
    CAST(NULL AS NUMBER(38, 0)) AS counted_units,
    -4 AS variance_units
)
