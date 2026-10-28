TEST (name "int_edge_quantity_checks__casts_text_only_after_filtering_out_non_numbers");

WITH __ref__stg_edge_ledger_entries AS (
  SELECT
    v.entry_id,
    NULL AS order_ref,
    NULL AS channel,
    NULL AS line_no,
    NULL AS sku,
    NULL AS warehouse_code,
    v.quantity::NUMBER(38, 0) AS quantity,
    v.quantity_text
  FROM VALUES
    ('LE-01', 7, '007'),
    ('LE-02', 7, '7.0'),
    ('LE-03', 7, ' 7 '),
    ('LE-04', 7, 'n/a'),
    ('LE-05', 7, '1e0'),
    ('LE-06', 7, '6.5'),
    ('LE-07', 7, ''),
    ('LE-08', 7, NULL) AS v(entry_id, quantity, quantity_text)
),

__expected__int_edge_quantity_checks AS (
  SELECT
    'LE-01' AS entry_id,
    '007' AS quantity_text,
    FALSE AS text_equals_seven,
    TRUE AS quantity_equals_seven_text,
    7 AS quantity_cast
  UNION ALL
  SELECT
    'LE-02' AS entry_id,
    '7.0' AS quantity_text,
    FALSE AS text_equals_seven,
    TRUE AS quantity_equals_seven_text,
    7 AS quantity_cast
  UNION ALL
  SELECT
    'LE-03' AS entry_id,
    ' 7 ' AS quantity_text,
    FALSE AS text_equals_seven,
    TRUE AS quantity_equals_seven_text,
    7 AS quantity_cast
  UNION ALL
  SELECT
    'LE-05' AS entry_id,
    '1e0' AS quantity_text,
    FALSE AS text_equals_seven,
    TRUE AS quantity_equals_seven_text,
    1 AS quantity_cast
  UNION ALL
  SELECT
    'LE-06' AS entry_id,
    '6.5' AS quantity_text,
    FALSE AS text_equals_seven,
    TRUE AS quantity_equals_seven_text,
    7 AS quantity_cast
)
