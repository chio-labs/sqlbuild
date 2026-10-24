TEST (name "stg_purchase_order_lines__explodes_po_lines_with_currency_override");

WITH __ref__stg_purchase_orders AS (
  SELECT
    'PO1' AS po_id,
    NULL AS supplier_code,
    NULL AS warehouse_code,
    'EUR' AS currency_code,
    NULL AS po_status,
    NULL AS ordered_at,
    NULL AS expected_at,
    NULL AS received_at,
    NULL AS line_count,
    ARRAY_CONSTRUCT(
      OBJECT_CONSTRUCT(
        'sku',
        'duck_mal 01',
        'qty',
        24,
        'unit_cost_minor',
        150
      ),
      OBJECT_CONSTRUCT(
        'sku',
        'DUCK-TEAL-02',
        'qty',
        6,
        'unit_cost',
        900,
        'currency',
        'gbp'
      )
    )::ARRAY AS lines,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'PO2',
    NULL,
    NULL,
    'EUR',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__expected__stg_purchase_order_lines AS (
  SELECT
    'PO1-000' AS po_line_key,
    'DUCK-MAL01' AS sku,
    24 AS ordered_qty,
    150 AS unit_cost_minor,
    'EUR' AS currency_code
  UNION ALL
  SELECT
    'PO1-001' AS po_line_key,
    'DUCK-TEAL-02' AS sku,
    6 AS ordered_qty,
    900 AS unit_cost_minor,
    'GBP' AS currency_code
)
