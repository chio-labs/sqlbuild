TEST (name "int_edge_payload_arrays__combines_codes_and_tags_with_nulls_and_duplicates");

WITH __ref__stg_edge_partner_payloads AS (
  SELECT
    'PM-1' AS message_id,
    PARSE_JSON(
      '{"promo_code": "SPRING", "gift_code": null, "tags": ["bath", "gift", "bath", null, '
        || '"bath"], "removed_tags": ["bath"], "extra_tags": ["gift", null]}'
    ) AS payload
  UNION ALL
  SELECT
    'PM-2',
    PARSE_JSON('{"promo_code": null, "tags": [], "removed_tags": [], "extra_tags": []}')
  UNION ALL
  SELECT
    'PM-3',
    PARSE_JSON(
      '{"gift_code": "GIFT-10", "tags": [1, 1.0, "1", {"b": 1, "a": 2}, {"a": 2, "b": 1}], '
        || '"removed_tags": [1.0, {"a": 2, "b": 1}], "extra_tags": [1e0]}'
    )
),

__expected__int_edge_payload_arrays AS (
  SELECT
    'PM-1' AS message_id,
    PARSE_JSON('["SPRING",undefined]')::ARRAY AS codes,
    PARSE_JSON('["SPRING"]')::ARRAY AS codes_compact,
    PARSE_JSON('["bath","gift","bath","bath"]')::ARRAY AS tags_compact,
    PARSE_JSON('["gift","bath",null,"bath"]')::ARRAY AS tags_kept,
    PARSE_JSON('["bath","gift","bath",null,"bath","gift",null]')::ARRAY AS tags_all,
    PARSE_JSON('["bath","gift",null]')::ARRAY AS tags_distinct,
    TRUE AS shares_extra_tags
  UNION ALL
  SELECT
    'PM-2' AS message_id,
    PARSE_JSON('[undefined,undefined]')::ARRAY AS codes,
    PARSE_JSON('[]')::ARRAY AS codes_compact,
    PARSE_JSON('[]')::ARRAY AS tags_compact,
    PARSE_JSON('[]')::ARRAY AS tags_kept,
    PARSE_JSON('[]')::ARRAY AS tags_all,
    PARSE_JSON('[]')::ARRAY AS tags_distinct,
    FALSE AS shares_extra_tags
  UNION ALL
  SELECT
    'PM-3' AS message_id,
    PARSE_JSON('[undefined,"GIFT-10"]')::ARRAY AS codes,
    PARSE_JSON('["GIFT-10"]')::ARRAY AS codes_compact,
    PARSE_JSON('[1,1,"1",{"a":2,"b":1},{"a":2,"b":1}]')::ARRAY AS tags_compact,
    PARSE_JSON('[1,"1",{"a":2,"b":1}]')::ARRAY AS tags_kept,
    PARSE_JSON('[1,1,"1",{"a":2,"b":1},{"a":2,"b":1},1.000000000000000e+00]')::ARRAY AS tags_all,
    PARSE_JSON('[1,"1",{"a":2,"b":1}]')::ARRAY AS tags_distinct,
    TRUE AS shares_extra_tags
)

TEST (name "int_edge_payload_arrays__matches_category_ids_across_number_spellings");

WITH __ref__stg_edge_partner_payloads AS (
  SELECT
    'PM-1' AS message_id,
    PARSE_JSON('{"category_id": 2, "eligible_ids": [1, 2.0, 3]}') AS payload
  UNION ALL
  SELECT
    'PM-2',
    PARSE_JSON('{"category_id": 3, "eligible_ids": [1, 2.0, 3e0]}')
  UNION ALL
  SELECT
    'PM-3',
    PARSE_JSON('{"category_id": "1", "eligible_ids": [1, 2.0, 3]}')
  UNION ALL
  SELECT
    'PM-4',
    PARSE_JSON('{"category_id": 1.0, "eligible_ids": [1, 2.0, 3]}')
  UNION ALL
  SELECT
    'PM-5',
    PARSE_JSON('{"category_id": 2.5, "eligible_ids": [2, 2.50, 3]}')
  UNION ALL
  SELECT
    'PM-6',
    PARSE_JSON('{"category_id": null, "eligible_ids": [null, 1]}')
  UNION ALL
  SELECT
    'PM-7',
    PARSE_JSON('{"category_id": 4, "eligible_ids": []}')
),

__expected__int_edge_payload_arrays AS (
  SELECT
    'PM-1' AS message_id,
    1 AS category_position,
    TRUE AS is_eligible
  UNION ALL
  SELECT
    'PM-2' AS message_id,
    2 AS category_position,
    TRUE AS is_eligible
  UNION ALL
  SELECT
    'PM-3' AS message_id,
    CAST(NULL AS NUMBER(38, 0)) AS category_position,
    FALSE AS is_eligible
  UNION ALL
  SELECT
    'PM-4' AS message_id,
    0 AS category_position,
    TRUE AS is_eligible
  UNION ALL
  SELECT
    'PM-5' AS message_id,
    1 AS category_position,
    TRUE AS is_eligible
  UNION ALL
  SELECT
    'PM-6' AS message_id,
    0 AS category_position,
    TRUE AS is_eligible
  UNION ALL
  SELECT
    'PM-7' AS message_id,
    CAST(NULL AS NUMBER(38, 0)) AS category_position,
    FALSE AS is_eligible
)
