TEST (name "int_edge_order_line_labels__lists_lines_in_a_total_order_and_summarises_prices");

WITH __ref__stg_edge_ledger_entries AS (
  SELECT
    v.entry_id,
    v.order_ref,
    NULL AS channel,
    v.line_no::NUMBER(38, 0) AS line_no,
    v.sku,
    NULL AS warehouse_code,
    v.quantity::NUMBER(38, 0) AS quantity,
    NULL AS quantity_text,
    NULL AS quantity_from_text,
    NULL AS quantity_text_decimal,
    v.unit_price_minor::NUMBER(38, 0) AS unit_price_minor,
    NULL AS amount,
    NULL AS currency_code,
    NULL AS fx_rate,
    NULL AS status,
    NULL AS reason_code,
    v.customer_tier
  FROM VALUES
    ('LE-01', 'DS-O-1', 2, 'TEAL-02', 1, 899, 'Mallard'),
    ('LE-02', 'DS-O-1', 1, 'MALLARD-01', 2, 1299, 'Mallard'),
    ('LE-03', 'DS-O-1', 1, 'EIDER-03', 2, 350, 'Mallard'),
    ('LE-04', 'DS-O-2', 1, 'PINTAIL-04', 1, 100, NULL),
    ('LE-05', 'DS-O-2', 2, 'PINTAIL-04', 3, 200, NULL),
    ('LE-06', 'DS-O-2', 3, NULL, 3, 300, NULL),
    ('LE-07', 'DS-O-2', 4, 'TEAL-02', 5, NULL, NULL),
    ('LE-08', 'DS-O-3', 1, 'MALLARD-01', 1, 500, 'Duckling'),
    ('LE-09', NULL, 1, 'TEAL-02', 1, 1, 'Duckling') AS v(entry_id, order_ref, line_no, sku, quantity, unit_price_minor, customer_tier)
),

__expected__int_edge_order_line_labels AS (
  SELECT
    'DS-O-1' AS order_ref,
    3 AS line_count,
    'EIDER-03,MALLARD-01,TEAL-02' AS sku_list,
    PARSE_JSON('["EIDER-03","MALLARD-01","TEAL-02"]')::ARRAY AS sku_array,
    'MALLARD-01' AS priciest_sku,
    'EIDER-03' AS cheapest_sku,
    'Mallard' AS customer_tier,
    899.000::NUMBER(38, 3) AS median_unit_price,
    624.500::NUMBER(38, 3) AS percentile_unit_price,
    350 AS percentile_disc_unit_price,
    2 AS modal_quantity
  UNION ALL
  SELECT
    'DS-O-2' AS order_ref,
    4 AS line_count,
    'PINTAIL-04,PINTAIL-04,TEAL-02' AS sku_list,
    PARSE_JSON('["PINTAIL-04","PINTAIL-04","TEAL-02"]')::ARRAY AS sku_array,
    CAST(NULL AS VARCHAR) AS priciest_sku,
    'PINTAIL-04' AS cheapest_sku,
    CAST(NULL AS VARCHAR) AS customer_tier,
    200.000::NUMBER(38, 3) AS median_unit_price,
    150.000::NUMBER(38, 3) AS percentile_unit_price,
    100 AS percentile_disc_unit_price,
    3 AS modal_quantity
  UNION ALL
  SELECT
    'DS-O-3' AS order_ref,
    1 AS line_count,
    'MALLARD-01' AS sku_list,
    PARSE_JSON('["MALLARD-01"]')::ARRAY AS sku_array,
    'MALLARD-01' AS priciest_sku,
    'MALLARD-01' AS cheapest_sku,
    'Duckling' AS customer_tier,
    500.000::NUMBER(38, 3) AS median_unit_price,
    500.000::NUMBER(38, 3) AS percentile_unit_price,
    500 AS percentile_disc_unit_price,
    1 AS modal_quantity
)

TEST (name "int_edge_order_line_labels__picks_one_of_the_tied_lines_for_max_by_and_mode");

WITH __ref__stg_edge_ledger_entries AS (
  SELECT
    v.entry_id,
    v.order_ref,
    NULL AS channel,
    v.line_no::NUMBER(38, 0) AS line_no,
    v.sku,
    NULL AS warehouse_code,
    v.quantity::NUMBER(38, 0) AS quantity,
    NULL AS quantity_text,
    NULL AS quantity_from_text,
    NULL AS quantity_text_decimal,
    v.unit_price_minor::NUMBER(38, 0) AS unit_price_minor,
    NULL AS amount,
    NULL AS currency_code,
    NULL AS fx_rate,
    NULL AS status,
    NULL AS reason_code,
    NULL AS customer_tier
  FROM VALUES
    ('LE-01', 'DS-O-1', 1, 'MALLARD-01', 1, 1299),
    ('LE-02', 'DS-O-1', 2, 'TEAL-02', 2, 1299),
    ('LE-03', 'DS-O-1', 3, 'EIDER-03', 1, 350),
    ('LE-04', 'DS-O-1', 4, 'PINTAIL-04', 2, 350) AS v(entry_id, order_ref, line_no, sku, quantity, unit_price_minor)
),

__expected__int_edge_order_line_labels AS (
  SELECT
    'DS-O-1' AS order_ref,
    4 AS line_count,
    'MALLARD-01,TEAL-02,EIDER-03,PINTAIL-04' AS sku_list,
    824.500::NUMBER(38, 3) AS median_unit_price
),

__assert__tied_picks_come_from_the_tied_lines AS (
  SELECT l.order_ref
  FROM __ref("int_edge_order_line_labels") AS l
  WHERE
    l.priciest_sku NOT IN ('MALLARD-01', 'TEAL-02')
    OR l.cheapest_sku NOT IN ('EIDER-03', 'PINTAIL-04')
    OR l.modal_quantity NOT IN (1, 2)
)
