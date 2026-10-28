TEST (name "int_edge_payload_attributes__reads_computed_keys_exactly_and_ignoring_case");

WITH __ref__stg_edge_partner_payloads AS (
  SELECT
    'PM-1' AS message_id,
    PARSE_JSON(
      '{"wanted": ["Size (cm)", "sku", "SKU", "a.b", "$discount", "", "*", "colour"], '
        || '"attrs": {"Size (cm)": "12", "Sku": "MALLARD-01", "a.b": "dotted", "a": {"b": "nested"}, '
        || '"$discount": "5%", "": "blank", "*": "star", "colour": null}}'
    ) AS payload
  UNION ALL
  SELECT
    'PM-2',
    PARSE_JSON('{"wanted": ["sku", "SKU"], "attrs": {"SKU": "TEAL-02", "sku": "teal-02"}}')
  UNION ALL
  SELECT
    'PM-3',
    PARSE_JSON('{"wanted": [], "attrs": {"sku": "EIDER-03"}}')
  UNION ALL
  SELECT
    'PM-4',
    PARSE_JSON('{"attrs": {"sku": "PINTAIL-04"}}')
),

__expected__int_edge_payload_attributes AS (
  SELECT
    'PM-1' AS message_id,
    0 AS wanted_index,
    'Size (cm)' AS attribute_name,
    '12' AS attribute_value,
    '12' AS attribute_value_any_case
  UNION ALL
  SELECT
    'PM-1' AS message_id,
    1 AS wanted_index,
    'sku' AS attribute_name,
    CAST(NULL AS VARCHAR) AS attribute_value,
    'MALLARD-01' AS attribute_value_any_case
  UNION ALL
  SELECT
    'PM-1' AS message_id,
    2 AS wanted_index,
    'SKU' AS attribute_name,
    CAST(NULL AS VARCHAR) AS attribute_value,
    'MALLARD-01' AS attribute_value_any_case
  UNION ALL
  SELECT
    'PM-1' AS message_id,
    3 AS wanted_index,
    'a.b' AS attribute_name,
    'dotted' AS attribute_value,
    'dotted' AS attribute_value_any_case
  UNION ALL
  SELECT
    'PM-1' AS message_id,
    4 AS wanted_index,
    '$discount' AS attribute_name,
    '5%' AS attribute_value,
    '5%' AS attribute_value_any_case
  UNION ALL
  SELECT
    'PM-1' AS message_id,
    5 AS wanted_index,
    '' AS attribute_name,
    'blank' AS attribute_value,
    'blank' AS attribute_value_any_case
  UNION ALL
  SELECT
    'PM-1' AS message_id,
    6 AS wanted_index,
    '*' AS attribute_name,
    'star' AS attribute_value,
    'star' AS attribute_value_any_case
  UNION ALL
  SELECT
    'PM-1' AS message_id,
    7 AS wanted_index,
    'colour' AS attribute_name,
    CAST(NULL AS VARCHAR) AS attribute_value,
    CAST(NULL AS VARCHAR) AS attribute_value_any_case
  UNION ALL
  SELECT
    'PM-2' AS message_id,
    0 AS wanted_index,
    'sku' AS attribute_name,
    'teal-02' AS attribute_value,
    'teal-02' AS attribute_value_any_case
  UNION ALL
  SELECT
    'PM-2' AS message_id,
    1 AS wanted_index,
    'SKU' AS attribute_name,
    'TEAL-02' AS attribute_value,
    'TEAL-02' AS attribute_value_any_case
)
