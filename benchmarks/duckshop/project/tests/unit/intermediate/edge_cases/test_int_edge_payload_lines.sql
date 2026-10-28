TEST (name "int_edge_payload_lines__keeps_messages_without_line_arrays_as_one_row");

WITH __ref__stg_edge_partner_payloads AS (
  SELECT
    'PM-1' AS message_id,
    PARSE_JSON('{"lines": [{"sku": "MALLARD-01"}, {"sku": "TEAL-02"}]}') AS payload
  UNION ALL
  SELECT
    'PM-2',
    PARSE_JSON('{"lines": []}')
  UNION ALL
  SELECT
    'PM-3',
    PARSE_JSON('{"lines": null}')
  UNION ALL
  SELECT
    'PM-4',
    PARSE_JSON('{}')
  UNION ALL
  SELECT
    'PM-5',
    PARSE_JSON('{"lines": {"sku": "EIDER-03", "qty": 1}}')
  UNION ALL
  SELECT
    'PM-6',
    PARSE_JSON('{"lines": [null, "PINTAIL-04"]}')
),

__expected__int_edge_payload_lines AS (
  SELECT
    'PM-1' AS message_id,
    0 AS line_index,
    CAST(NULL AS VARCHAR) AS line_key,
    '[0]' AS line_path,
    'OBJECT' AS line_kind,
    'MALLARD-01' AS line_sku
  UNION ALL
  SELECT
    'PM-1' AS message_id,
    1 AS line_index,
    CAST(NULL AS VARCHAR) AS line_key,
    '[1]' AS line_path,
    'OBJECT' AS line_kind,
    'TEAL-02' AS line_sku
  UNION ALL
  SELECT
    'PM-2' AS message_id,
    CAST(NULL AS NUMBER(38, 0)) AS line_index,
    CAST(NULL AS VARCHAR) AS line_key,
    '' AS line_path,
    CAST(NULL AS VARCHAR) AS line_kind,
    CAST(NULL AS VARCHAR) AS line_sku
  UNION ALL
  SELECT
    'PM-3' AS message_id,
    CAST(NULL AS NUMBER(38, 0)) AS line_index,
    CAST(NULL AS VARCHAR) AS line_key,
    CAST(NULL AS VARCHAR) AS line_path,
    CAST(NULL AS VARCHAR) AS line_kind,
    CAST(NULL AS VARCHAR) AS line_sku
  UNION ALL
  SELECT
    'PM-4' AS message_id,
    CAST(NULL AS NUMBER(38, 0)) AS line_index,
    CAST(NULL AS VARCHAR) AS line_key,
    CAST(NULL AS VARCHAR) AS line_path,
    CAST(NULL AS VARCHAR) AS line_kind,
    CAST(NULL AS VARCHAR) AS line_sku
  UNION ALL
  SELECT
    'PM-5' AS message_id,
    CAST(NULL AS NUMBER(38, 0)) AS line_index,
    'qty' AS line_key,
    'qty' AS line_path,
    'INTEGER' AS line_kind,
    CAST(NULL AS VARCHAR) AS line_sku
  UNION ALL
  SELECT
    'PM-5' AS message_id,
    CAST(NULL AS NUMBER(38, 0)) AS line_index,
    'sku' AS line_key,
    'sku' AS line_path,
    'VARCHAR' AS line_kind,
    CAST(NULL AS VARCHAR) AS line_sku
  UNION ALL
  SELECT
    'PM-6' AS message_id,
    0 AS line_index,
    CAST(NULL AS VARCHAR) AS line_key,
    '[0]' AS line_path,
    'NULL_VALUE' AS line_kind,
    CAST(NULL AS VARCHAR) AS line_sku
  UNION ALL
  SELECT
    'PM-6' AS message_id,
    1 AS line_index,
    CAST(NULL AS VARCHAR) AS line_key,
    '[1]' AS line_path,
    'VARCHAR' AS line_kind,
    CAST(NULL AS VARCHAR) AS line_sku
)
