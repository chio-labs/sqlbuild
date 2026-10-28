TEST (name "int_edge_payload_objects__builds_summaries_that_drop_or_keep_nulls");

WITH __ref__stg_edge_partner_payloads AS (
  SELECT
    'PM-1' AS message_id,
    PARSE_JSON('{"channel": "web", "sku": "MALLARD-01", "qty": 2, "currency": "GBP"}') AS payload
  UNION ALL
  SELECT
    'PM-2',
    PARSE_JSON('{"channel": null, "sku": "TEAL-02", "qty": null, "currency": null}')
  UNION ALL
  SELECT
    'PM-3',
    PARSE_JSON('{"sku": "EIDER-03"}')
),

__expected__int_edge_payload_objects AS (
  SELECT
    'PM-1' AS message_id,
    PARSE_JSON('{"channel":"web","qty":2,"sku":"MALLARD-01"}')::OBJECT AS order_summary,
    PARSE_JSON('{"channel":"web","qty":2,"sku":"MALLARD-01"}')::OBJECT AS order_summary_keep_null,
    PARSE_JSON('{"currency":"GBP"}')::OBJECT AS currency_object
  UNION ALL
  SELECT
    'PM-2' AS message_id,
    PARSE_JSON('{"qty":null,"sku":"TEAL-02"}')::OBJECT AS order_summary,
    PARSE_JSON('{"channel":null,"qty":null,"sku":"TEAL-02"}')::OBJECT AS order_summary_keep_null,
    PARSE_JSON('{}')::OBJECT AS currency_object
  UNION ALL
  SELECT
    'PM-3' AS message_id,
    PARSE_JSON('{"sku":"EIDER-03"}')::OBJECT AS order_summary,
    PARSE_JSON('{"channel":null,"qty":null,"sku":"EIDER-03"}')::OBJECT AS order_summary_keep_null,
    PARSE_JSON('{}')::OBJECT AS currency_object
)

TEST (name "int_edge_payload_objects__normalises_payloads_by_inserting_deleting_and_picking_keys");

WITH __ref__stg_edge_partner_payloads AS (
  SELECT
    'PM-1' AS message_id,
    PARSE_JSON(
      '{"meta": {"order_id": "DS-O-1001"}, "a.b": 1, "a": {"b": 2}, "lines": [1], '
        || '"gift_note": "Happy quacking", "pick_keys": ["sku", "lines", "missing"], '
        || '"sku": "MALLARD-01"}'
    ) AS payload
  UNION ALL
  SELECT
    'PM-2',
    PARSE_JSON('{"orderId": "DS-O-0999", "meta": {}, "gift_note": null, "pick_keys": [], "sku": "TEAL-02"}')
  UNION ALL
  SELECT
    'PM-3',
    PARSE_JSON('{"orderId": "DS-O-1002", "Meta": {"order_id": "upper"}, "lines": null}')
),

__expected__int_edge_payload_objects AS (
  SELECT
    'PM-1' AS message_id,
    PARSE_JSON(
      '{"a":{"b":2},"gift_note":"Happy quacking","lines":[1],"orderId":"DS-O-1001",'
        || '"pick_keys":["sku","lines","missing"],"sku":"MALLARD-01"}'
    )::OBJECT AS normalised_payload,
    PARSE_JSON(
      '{"a":{"b":2},"gift_note":"Happy quacking","lines":[1],"orderId":"DS-O-1001",'
        || '"pick_keys":["sku","lines","missing"],"sku":"MALLARD-01"}'
    )::OBJECT AS gift_note_updated,
    PARSE_JSON('{"lines":[1],"orderId":"DS-O-1001"}')::OBJECT AS picked_payload,
    PARSE_JSON('{"lines":[1],"sku":"MALLARD-01"}')::OBJECT AS picked_by_array,
    PARSE_JSON('{}')::OBJECT AS picked_by_variant,
    PARSE_JSON('["a","a.b","gift_note","lines","meta","pick_keys","sku"]')::ARRAY AS payload_keys
  UNION ALL
  SELECT
    'PM-2' AS message_id,
    PARSE_JSON('{"gift_note":null,"pick_keys":[],"sku":"TEAL-02"}')::OBJECT AS normalised_payload,
    PARSE_JSON('{"pick_keys":[],"sku":"TEAL-02"}')::OBJECT AS gift_note_updated,
    PARSE_JSON('{}')::OBJECT AS picked_payload,
    PARSE_JSON('{}')::OBJECT AS picked_by_array,
    PARSE_JSON('{}')::OBJECT AS picked_by_variant,
    PARSE_JSON('["gift_note","meta","orderId","pick_keys","sku"]')::ARRAY AS payload_keys
  UNION ALL
  SELECT
    'PM-3' AS message_id,
    PARSE_JSON('{"Meta":{"order_id":"upper"},"lines":null}')::OBJECT AS normalised_payload,
    PARSE_JSON('{"Meta":{"order_id":"upper"},"lines":null}')::OBJECT AS gift_note_updated,
    PARSE_JSON('{"lines":null}')::OBJECT AS picked_payload,
    PARSE_JSON('{}')::OBJECT AS picked_by_array,
    PARSE_JSON('{}')::OBJECT AS picked_by_variant,
    PARSE_JSON('["Meta","lines","orderId"]')::ARRAY AS payload_keys
)
