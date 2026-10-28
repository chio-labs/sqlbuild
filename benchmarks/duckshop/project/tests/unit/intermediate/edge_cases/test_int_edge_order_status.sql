TEST (name "int_edge_order_status__orders_by_the_raw_status_not_the_upper_cased_alias");

WITH __ref__stg_edge_ledger_entries AS (
  SELECT
    v.entry_id,
    v.order_ref,
    NULL AS channel,
    NULL AS line_no,
    NULL AS sku,
    NULL AS warehouse_code,
    NULL AS quantity,
    NULL AS quantity_text,
    NULL AS quantity_from_text,
    NULL AS quantity_text_decimal,
    NULL AS unit_price_minor,
    NULL AS amount,
    NULL AS currency_code,
    NULL AS fx_rate,
    v.status
  FROM VALUES
    ('LE-01', 'DS-O-1', 'pending'),
    ('LE-02', 'DS-O-1', 'shipped'),
    ('LE-03', 'DS-O-2', 'Pending'),
    ('LE-04', 'DS-O-2', 'SHIPPED'),
    ('LE-05', 'DS-O-3', 'pending'),
    ('LE-06', 'DS-O-3', 'cancelled'),
    ('LE-07', 'DS-O-4', NULL),
    ('LE-08', 'DS-O-4', 'Shipped') AS v(entry_id, order_ref, status)
),

__expected__int_edge_order_status AS (
  SELECT
    'DS-O-1' AS order_ref,
    'PENDING' AS status,
    'LE-01' AS entry_id
  UNION ALL
  SELECT
    'DS-O-2' AS order_ref,
    'SHIPPED' AS status,
    'LE-04' AS entry_id
  UNION ALL
  SELECT
    'DS-O-3' AS order_ref,
    'PENDING' AS status,
    'LE-05' AS entry_id
  UNION ALL
  SELECT
    'DS-O-4' AS order_ref,
    CAST(NULL AS VARCHAR) AS status,
    'LE-07' AS entry_id
)
