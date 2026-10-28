TEST (name "int_edge_payload_tags__splits_tag_text_keeping_empty_tags");

WITH __ref__stg_edge_partner_payloads AS (
  SELECT
    'PM-1' AS message_id,
    PARSE_JSON('{"tags_text": "bath,,gift"}') AS payload
  UNION ALL
  SELECT
    'PM-2',
    PARSE_JSON('{"tags_text": ""}')
  UNION ALL
  SELECT
    'PM-3',
    PARSE_JSON('{"tags_text": null}')
  UNION ALL
  SELECT
    'PM-4',
    PARSE_JSON('{"tags_text": " bath , gift,"}')
),

__expected__int_edge_payload_tags AS (
  SELECT
    'PM-1' AS message_id,
    1 AS tag_index,
    'bath' AS tag
  UNION ALL
  SELECT
    'PM-1' AS message_id,
    2 AS tag_index,
    '' AS tag
  UNION ALL
  SELECT
    'PM-1' AS message_id,
    3 AS tag_index,
    'gift' AS tag
  UNION ALL
  SELECT
    'PM-2' AS message_id,
    1 AS tag_index,
    '' AS tag
  UNION ALL
  SELECT
    'PM-4' AS message_id,
    1 AS tag_index,
    ' bath ' AS tag
  UNION ALL
  SELECT
    'PM-4' AS message_id,
    2 AS tag_index,
    ' gift' AS tag
  UNION ALL
  SELECT
    'PM-4' AS message_id,
    3 AS tag_index,
    '' AS tag
)
