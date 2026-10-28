TEST (name "int_edge_orders_all_channels__unions_channels_by_column_name");

WITH __ref__stg_edge_ledger_entries AS (
  SELECT
    v.entry_id,
    v.order_ref,
    v.channel,
    NULL AS line_no,
    NULL AS sku,
    NULL AS warehouse_code,
    v.quantity::NUMBER(38, 0) AS quantity,
    NULL AS quantity_text,
    NULL AS quantity_from_text,
    NULL AS quantity_text_decimal,
    NULL AS unit_price_minor,
    v.amount::NUMBER(38, 10) AS amount,
    NULL AS currency_code,
    v.fx_rate::FLOAT AS fx_rate,
    NULL AS status,
    v.reason_code
  FROM VALUES
    ('LE-01', 'DS-O-1', 'web', 2, '25.98', 1.0, 'REFUND'),
    ('LE-02', 'DS-O-2', 'app', 1, '8.99', 1.234567, NULL),
    ('LE-03', 'DS-O-3', 'partner', 5, '55', 0.66, 'DAMAGED'),
    ('LE-04', 'DS-O-4', 'phone', 1, '1', 1.0, NULL),
    ('LE-05', 'DS-O-5', 'app', 3, '-2.5', 0.000005, 'REFUND') AS v(entry_id, order_ref, channel, quantity, amount, fx_rate, reason_code)
),

__expected__int_edge_orders_all_channels AS (
  SELECT
    'LE-01' AS entry_id,
    'web' AS channel,
    'DS-O-1' AS order_ref,
    2 AS quantity,
    25.9800000000::NUMBER(38, 10) AS amount,
    'REFUND' AS refund_reason,
    1.0000000000::NUMBER(38, 10) AS rate
  UNION ALL
  SELECT
    'LE-02' AS entry_id,
    'app' AS channel,
    'DS-O-2' AS order_ref,
    1 AS quantity,
    8.9900000000::NUMBER(38, 10) AS amount,
    CAST(NULL AS VARCHAR) AS refund_reason,
    1.2345700000::NUMBER(38, 10) AS rate
  UNION ALL
  SELECT
    'LE-03' AS entry_id,
    'partner' AS channel,
    'DS-O-3' AS order_ref,
    5 AS quantity,
    55.0000000000::NUMBER(38, 10) AS amount,
    CAST(NULL AS VARCHAR) AS refund_reason,
    CAST(NULL AS NUMBER(38, 10)) AS rate
  UNION ALL
  SELECT
    'LE-05' AS entry_id,
    'app' AS channel,
    'DS-O-5' AS order_ref,
    3 AS quantity,
    -2.5000000000::NUMBER(38, 10) AS amount,
    'REFUND' AS refund_reason,
    0.0000100000::NUMBER(38, 10) AS rate
)
