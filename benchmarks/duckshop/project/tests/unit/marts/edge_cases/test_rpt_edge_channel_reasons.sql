TEST (name "rpt_edge_channel_reasons__aggregates_empty_and_all_missing_groups");

WITH __ref__stg_edge_ledger_entries AS (
  SELECT
    v.entry_id,
    NULL AS order_ref,
    v.channel,
    NULL AS line_no,
    NULL AS sku,
    NULL AS warehouse_code,
    v.quantity::NUMBER(38, 0) AS quantity,
    NULL AS quantity_text,
    NULL AS quantity_from_text,
    NULL AS quantity_text_decimal,
    NULL AS unit_price_minor,
    NULL AS amount,
    NULL AS currency_code,
    NULL AS fx_rate,
    NULL AS status,
    v.reason_code
  FROM VALUES
    ('LE-01', 'web', 2, 'REFUND'),
    ('LE-02', 'web', 1, 'DAMAGED'),
    ('LE-03', 'web', NULL, NULL),
    ('LE-04', 'app', 1, NULL),
    ('LE-05', 'app', 3, NULL),
    ('LE-06', 'catalogue', 1, 'REFUND') AS v(entry_id, channel, quantity, reason_code)
),

__expected__rpt_edge_channel_reasons AS (
  SELECT
    'app' AS channel,
    2 AS lines,
    0 AS reasons,
    0 AS refunded_lines,
    CAST(NULL AS BOOLEAN) AS any_refund,
    4 AS total_quantity,
    CAST(NULL AS VARCHAR) AS max_reason,
    '' AS reason_list,
    PARSE_JSON('[]')::ARRAY AS reason_array,
    PARSE_JSON('{}')::OBJECT AS reasons_by_entry
  UNION ALL
  SELECT
    'partner' AS channel,
    0 AS lines,
    0 AS reasons,
    0 AS refunded_lines,
    CAST(NULL AS BOOLEAN) AS any_refund,
    CAST(NULL AS NUMBER(38, 0)) AS total_quantity,
    CAST(NULL AS VARCHAR) AS max_reason,
    '' AS reason_list,
    PARSE_JSON('[]')::ARRAY AS reason_array,
    PARSE_JSON('{}')::OBJECT AS reasons_by_entry
  UNION ALL
  SELECT
    'phone' AS channel,
    0 AS lines,
    0 AS reasons,
    0 AS refunded_lines,
    CAST(NULL AS BOOLEAN) AS any_refund,
    CAST(NULL AS NUMBER(38, 0)) AS total_quantity,
    CAST(NULL AS VARCHAR) AS max_reason,
    '' AS reason_list,
    PARSE_JSON('[]')::ARRAY AS reason_array,
    PARSE_JSON('{}')::OBJECT AS reasons_by_entry
  UNION ALL
  SELECT
    'web' AS channel,
    3 AS lines,
    2 AS reasons,
    1 AS refunded_lines,
    TRUE AS any_refund,
    3 AS total_quantity,
    'REFUND' AS max_reason,
    'REFUND,DAMAGED' AS reason_list,
    PARSE_JSON('["REFUND","DAMAGED"]')::ARRAY AS reason_array,
    PARSE_JSON('{"LE-01":"REFUND","LE-02":"DAMAGED"}')::OBJECT AS reasons_by_entry
)

TEST (name "rpt_edge_channel_reasons__reports_every_channel_without_any_lines");

WITH __ref__stg_edge_ledger_entries AS (
  SELECT
    CAST(NULL AS VARCHAR) AS entry_id,
    CAST(NULL AS VARCHAR) AS order_ref,
    CAST(NULL AS VARCHAR) AS channel,
    CAST(NULL AS NUMBER(38, 0)) AS line_no,
    CAST(NULL AS VARCHAR) AS sku,
    CAST(NULL AS VARCHAR) AS warehouse_code,
    CAST(NULL AS NUMBER(38, 0)) AS quantity,
    CAST(NULL AS VARCHAR) AS quantity_text,
    CAST(NULL AS NUMBER(18, 2)) AS quantity_from_text,
    CAST(NULL AS NUMBER(18, 0)) AS quantity_text_decimal,
    CAST(NULL AS NUMBER(38, 0)) AS unit_price_minor,
    CAST(NULL AS NUMBER(38, 10)) AS amount,
    CAST(NULL AS VARCHAR) AS currency_code,
    CAST(NULL AS FLOAT) AS fx_rate,
    CAST(NULL AS VARCHAR) AS status,
    CAST(NULL AS VARCHAR) AS reason_code
  WHERE FALSE
),

__expected__rpt_edge_channel_reasons AS (
  SELECT
    'app' AS channel,
    0 AS lines,
    0 AS reasons,
    0 AS refunded_lines,
    CAST(NULL AS BOOLEAN) AS any_refund,
    CAST(NULL AS NUMBER(38, 0)) AS total_quantity,
    CAST(NULL AS VARCHAR) AS max_reason,
    '' AS reason_list,
    PARSE_JSON('[]')::ARRAY AS reason_array,
    PARSE_JSON('{}')::OBJECT AS reasons_by_entry
  UNION ALL
  SELECT
    'partner' AS channel,
    0 AS lines,
    0 AS reasons,
    0 AS refunded_lines,
    CAST(NULL AS BOOLEAN) AS any_refund,
    CAST(NULL AS NUMBER(38, 0)) AS total_quantity,
    CAST(NULL AS VARCHAR) AS max_reason,
    '' AS reason_list,
    PARSE_JSON('[]')::ARRAY AS reason_array,
    PARSE_JSON('{}')::OBJECT AS reasons_by_entry
  UNION ALL
  SELECT
    'phone' AS channel,
    0 AS lines,
    0 AS reasons,
    0 AS refunded_lines,
    CAST(NULL AS BOOLEAN) AS any_refund,
    CAST(NULL AS NUMBER(38, 0)) AS total_quantity,
    CAST(NULL AS VARCHAR) AS max_reason,
    '' AS reason_list,
    PARSE_JSON('[]')::ARRAY AS reason_array,
    PARSE_JSON('{}')::OBJECT AS reasons_by_entry
  UNION ALL
  SELECT
    'web' AS channel,
    0 AS lines,
    0 AS reasons,
    0 AS refunded_lines,
    CAST(NULL AS BOOLEAN) AS any_refund,
    CAST(NULL AS NUMBER(38, 0)) AS total_quantity,
    CAST(NULL AS VARCHAR) AS max_reason,
    '' AS reason_list,
    PARSE_JSON('[]')::ARRAY AS reason_array,
    PARSE_JSON('{}')::OBJECT AS reasons_by_entry
)
