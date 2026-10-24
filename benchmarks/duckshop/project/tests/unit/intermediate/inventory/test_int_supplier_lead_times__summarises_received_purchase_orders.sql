TEST (name "int_supplier_lead_times__summarises_received_purchase_orders");

WITH __ref__int_purchase_order_lines_received AS (
  SELECT
    'PO1#1' AS po_line_key,
    'PO1' AS po_id,
    NULL AS supplier_code,
    NULL AS warehouse_code,
    NULL AS sku,
    10 AS ordered_qty,
    10 AS received_qty,
    NULL AS damaged_qty,
    NULL AS outstanding_qty,
    NULL AS fill_rate,
    NULL AS first_received_at_local,
    0 AS days_late,
    NULL AS receipt_count,
    NULL AS discrepancy_codes
  UNION ALL
  SELECT
    'PO2#1',
    'PO2',
    NULL,
    NULL,
    NULL,
    10,
    5,
    NULL,
    NULL,
    NULL,
    NULL,
    3,
    NULL,
    NULL
),

__ref__stg_purchase_orders AS (
  SELECT
    'PO1' AS po_id,
    'SUP1' AS supplier_code,
    NULL AS warehouse_code,
    NULL AS currency_code,
    NULL AS po_status,
    '2026-03-01 00:00:00 +00:00'::TIMESTAMP_TZ AS ordered_at,
    NULL AS expected_at,
    '2026-03-11 00:00:00 +00:00'::TIMESTAMP_TZ AS received_at,
    NULL AS line_count,
    NULL AS lines,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'PO2',
    'SUP1',
    NULL,
    NULL,
    NULL,
    '2026-03-05 00:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    '2026-03-25 12:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'PO3',
    'SUP1',
    NULL,
    NULL,
    NULL,
    '2026-03-20 00:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_suppliers AS (
  SELECT
    'SUP1' AS supplier_code,
    'Teal Hollow Decoys' AS supplier_name,
    NULL AS country_code,
    NULL AS payment_terms_days,
    NULL AS early_payment_discount_pct,
    NULL AS primary_contact_email,
    NULL AS contact_count,
    NULL AS payment_terms,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__expected__int_supplier_lead_times AS (
  SELECT
    'SUP1' AS supplier_code,
    'Teal Hollow Decoys' AS supplier_name,
    2 AS received_po_count,
    15.25::DECIMAL(10, 2) AS lead_time_p50_days,
    19.45::DECIMAL(10, 2) AS lead_time_p90_days,
    7.42::DECIMAL(10, 2) AS lead_time_stddev_days,
    0.5::DECIMAL(9, 4) AS on_time_rate,
    0.75::DECIMAL(9, 4) AS avg_fill_rate,
    '2026-03-05 00:00:00 +00:00'::TIMESTAMP_TZ AS latest_po_at
)
