TEST (name "stg_ticket_tags__merges_array_tags_and_label_field");

WITH __ref__stg_tickets AS (
  SELECT
    'T1' AS ticket_id,
    NULL AS customer_email,
    NULL AS channel,
    NULL AS priority,
    NULL AS ticket_status,
    NULL AS created_at,
    NULL AS solved_at,
    NULL AS order_id,
    NULL AS contact_reason,
    PARSE_JSON('["Damaged Item", "damaged_item", null, "  "]')::ARRAY AS tag_list,
    NULL AS is_vip,
    PARSE_JSON('{"labels": "vip, Rubber Ducks"}')::OBJECT AS custom_fields,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'T2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    PARSE_JSON('[]')::ARRAY,
    NULL,
    PARSE_JSON('{}')::OBJECT,
    NULL,
    NULL
),

__expected__stg_ticket_tags AS (
  SELECT
    'T1:damaged-item' AS ticket_tag_key,
    'damaged-item' AS tag
  UNION ALL
  SELECT
    'T1:vip' AS ticket_tag_key,
    'vip' AS tag
  UNION ALL
  SELECT
    'T1:rubber-ducks' AS ticket_tag_key,
    'rubber-ducks' AS tag
)
