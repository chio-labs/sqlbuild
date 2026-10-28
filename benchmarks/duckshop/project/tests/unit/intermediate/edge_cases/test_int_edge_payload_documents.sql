TEST (name "int_edge_payload_documents__writes_documents_with_sorted_keys_and_escapes");

WITH __ref__stg_edge_partner_payloads AS (
  SELECT
    'PM-1' AS message_id,
    PARSE_JSON('{"sku": "MALLARD-01", "qty": 2, "Attrs": {"sku": "a", "SKU": "b"}}') AS payload,
    CAST(NULL AS VARIANT) AS text_payload
  UNION ALL
  SELECT
    'PM-2',
    PARSE_JSON('{"items": [{"qty": 1}, {"QTY": 2}], "b": 1, "a": {"z": 1, "y": 2}}'),
    NULL
  UNION ALL
  SELECT
    'PM-3',
    PARSE_JSON('{"\\u00e9": "precomposed", "e\\u0301": "combining", "_": 1, "Z": 2, "a": 3}'),
    NULL
  UNION ALL
  SELECT
    'PM-4',
    PARSE_JSON('{"note": "unit\\u001fseparator", "line": "para\\u2028graph", "path": "a\\\\b \\"quoted\\" /"}'),
    NULL
),

__expected__int_edge_payload_documents AS (
  SELECT
    'PM-1' AS message_id,
    '{"Attrs":{"SKU":"b","sku":"a"},"qty":2,"sku":"MALLARD-01"}' AS payload_json,
    '{"Attrs":{"SKU":"b","sku":"a"},"qty":2,"sku":"MALLARD-01"}' AS payload_text_cast,
    '1f7dde3ac20d13ae115fb2d5e225d698' AS payload_md5
  UNION ALL
  SELECT
    'PM-2' AS message_id,
    '{"a":{"y":2,"z":1},"b":1,"items":[{"qty":1},{"QTY":2}]}' AS payload_json,
    '{"a":{"y":2,"z":1},"b":1,"items":[{"qty":1},{"QTY":2}]}' AS payload_text_cast,
    '565e04373d88d13210a746e00e30f9a6' AS payload_md5
  UNION ALL
  SELECT
    'PM-3' AS message_id,
    '{"Z":2,"_":1,"a":3,"e\u0301":"combining","é":"precomposed"}' AS payload_json,
    '{"Z":2,"_":1,"a":3,"e\u0301":"combining","é":"precomposed"}' AS payload_text_cast,
    '40585679ec958a682a75265757a619d4' AS payload_md5
  UNION ALL
  SELECT
    'PM-4' AS message_id,
    '{"line":"para\u2028graph","note":"unit\\u001fseparator","path":"a\\\\b \\"quoted\\" /"}' AS payload_json,
    '{"line":"para\u2028graph","note":"unit\\u001fseparator","path":"a\\\\b \\"quoted\\" /"}' AS payload_text_cast,
    '903fbf2b725c8f036f83e967faece91d' AS payload_md5
)

TEST (name "int_edge_payload_documents__tells_json_null_from_missing_and_sql_null");

WITH __ref__stg_edge_partner_payloads AS (
  SELECT
    'PM-1' AS message_id,
    PARSE_JSON('{"colour": null}') AS payload,
    CAST(NULL AS VARIANT) AS text_payload
  UNION ALL
  SELECT
    'PM-2',
    PARSE_JSON('{}'),
    NULL
  UNION ALL
  SELECT
    'PM-3',
    PARSE_JSON('{"colour": "teal"}'),
    NULL
  UNION ALL
  SELECT
    'PM-4',
    CAST(NULL AS VARIANT),
    NULL
  UNION ALL
  SELECT
    'PM-5',
    PARSE_JSON('{"colour": ""}'),
    NULL
  UNION ALL
  SELECT
    'PM-6',
    PARSE_JSON('{"colour": ["teal", null]}'),
    NULL
),

__expected__int_edge_payload_documents AS (
  SELECT
    'PM-1' AS message_id,
    TRUE AS colour_is_json_null,
    'NULL_VALUE' AS colour_kind,
    CAST(NULL AS VARCHAR) AS colour_text,
    'null' AS colour_json,
    FALSE AS colour_is_missing,
    'undyed' AS colour_or_default
  UNION ALL
  SELECT
    'PM-2' AS message_id,
    CAST(NULL AS BOOLEAN) AS colour_is_json_null,
    CAST(NULL AS VARCHAR) AS colour_kind,
    CAST(NULL AS VARCHAR) AS colour_text,
    CAST(NULL AS VARCHAR) AS colour_json,
    TRUE AS colour_is_missing,
    'undyed' AS colour_or_default
  UNION ALL
  SELECT
    'PM-3' AS message_id,
    FALSE AS colour_is_json_null,
    'VARCHAR' AS colour_kind,
    'teal' AS colour_text,
    '"teal"' AS colour_json,
    FALSE AS colour_is_missing,
    'teal' AS colour_or_default
  UNION ALL
  SELECT
    'PM-4' AS message_id,
    CAST(NULL AS BOOLEAN) AS colour_is_json_null,
    CAST(NULL AS VARCHAR) AS colour_kind,
    CAST(NULL AS VARCHAR) AS colour_text,
    CAST(NULL AS VARCHAR) AS colour_json,
    TRUE AS colour_is_missing,
    'undyed' AS colour_or_default
  UNION ALL
  SELECT
    'PM-5' AS message_id,
    FALSE AS colour_is_json_null,
    'VARCHAR' AS colour_kind,
    '' AS colour_text,
    '""' AS colour_json,
    FALSE AS colour_is_missing,
    '' AS colour_or_default
  UNION ALL
  SELECT
    'PM-6' AS message_id,
    FALSE AS colour_is_json_null,
    'ARRAY' AS colour_kind,
    '["teal",null]' AS colour_text,
    '["teal",null]' AS colour_json,
    FALSE AS colour_is_missing,
    '["teal",null]' AS colour_or_default
)

TEST (name "int_edge_payload_documents__reads_attribute_names_that_look_like_paths");

WITH __ref__stg_edge_partner_payloads AS (
  SELECT
    'PM-1' AS message_id,
    PARSE_JSON(
      '{"attrs": {"Size (cm)": "12", "a.b": "dotted", "a": {"b": "nested"}, "$discount": "5%", '
        || '"": "blank", "*": "star", "$.a": "dollar path", "Sku": "MALLARD-01"}}'
    ) AS payload,
    CAST(NULL AS VARIANT) AS text_payload
  UNION ALL
  SELECT
    'PM-2',
    PARSE_JSON('{"attrs": {"a": {"b": "nested only"}, "SKU": "TEAL-02", "sku": "teal-02"}}'),
    NULL
  UNION ALL
  SELECT
    'PM-3',
    PARSE_JSON('{"attrs": "not an object"}'),
    NULL
),

__expected__int_edge_payload_documents AS (
  SELECT
    'PM-1' AS message_id,
    '12' AS size_cm,
    'dotted' AS dotted_attribute,
    '5%' AS discount_attribute,
    'blank' AS empty_attribute,
    'star' AS star_attribute,
    'dollar path' AS path_like_attribute,
    'MALLARD-01' AS sku_any_case
  UNION ALL
  SELECT
    'PM-2' AS message_id,
    CAST(NULL AS VARCHAR) AS size_cm,
    CAST(NULL AS VARCHAR) AS dotted_attribute,
    CAST(NULL AS VARCHAR) AS discount_attribute,
    CAST(NULL AS VARCHAR) AS empty_attribute,
    CAST(NULL AS VARCHAR) AS star_attribute,
    CAST(NULL AS VARCHAR) AS path_like_attribute,
    'TEAL-02' AS sku_any_case
  UNION ALL
  SELECT
    'PM-3' AS message_id,
    CAST(NULL AS VARCHAR) AS size_cm,
    CAST(NULL AS VARCHAR) AS dotted_attribute,
    CAST(NULL AS VARCHAR) AS discount_attribute,
    CAST(NULL AS VARCHAR) AS empty_attribute,
    CAST(NULL AS VARCHAR) AS star_attribute,
    CAST(NULL AS VARCHAR) AS path_like_attribute,
    CAST(NULL AS VARCHAR) AS sku_any_case
)

TEST (name "int_edge_payload_documents__writes_text_payloads_and_tag_lists");

WITH __ref__stg_edge_partner_payloads AS (
  SELECT
    'PM-1' AS message_id,
    PARSE_JSON('{"tags": ["bath", null, "say \\"hi\\"", "a\\\\b", 7, ""]}') AS payload,
    PARSE_JSON('"{\\"orderId\\": \\"DS-O-1001\\"}"') AS text_payload
  UNION ALL
  SELECT
    'PM-2',
    PARSE_JSON('{"tags": []}'),
    PARSE_JSON('null')
  UNION ALL
  SELECT
    'PM-3',
    PARSE_JSON('{"tags": [1.50, true, {"b": 1, "a": 2}]}'),
    PARSE_JSON('{"b": 2, "a": [1.50, 1e2, -0.0]}')
),

__expected__int_edge_payload_documents AS (
  SELECT
    'PM-1' AS message_id,
    'bath|say "hi"|a\\b|7|' AS tag_list,
    '"{\\"orderId\\": \\"DS-O-1001\\"}"' AS text_payload_json,
    'VARCHAR' AS text_payload_kind
  UNION ALL
  SELECT
    'PM-2' AS message_id,
    '' AS tag_list,
    'null' AS text_payload_json,
    'NULL_VALUE' AS text_payload_kind
  UNION ALL
  SELECT
    'PM-3' AS message_id,
    '1.5|true|{"a":2,"b":1}' AS tag_list,
    '{"a":[1.5,1.000000000000000e+02,0],"b":2}' AS text_payload_json,
    'OBJECT' AS text_payload_kind
)
