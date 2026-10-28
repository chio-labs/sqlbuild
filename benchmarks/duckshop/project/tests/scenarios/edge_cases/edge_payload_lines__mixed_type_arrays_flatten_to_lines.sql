SCENARIO (
  description """
    Partner payloads whose line arrays mix numbers, objects and JSON nulls flatten to one row per
    line, and every output column of the published event documents is compared, VARIANT included
  """,
  tags ["edge_case"],
  expected_columns "all",
);

WITH __source__edge__partner_payloads AS (
  SELECT
    v.delivery_id,
    v.message_id,
    v.partner_code,
    NULL::TIMESTAMP_NTZ AS received_at,
    PARSE_JSON(v.payload) AS payload,
    NULL::VARCHAR AS payload_text,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  FROM VALUES
    ('DL-1', 'PM-1', 'mkt_eu', '{"lines": [1, {"sku": "MALLARD-01"}], "channel": "web"}'),
    ('DL-2', 'PM-2', 'giftbox', '{"lines": [{"sku": "TEAL-02", "y": [1, {"z": 2}]}, null]}') AS v(delivery_id, message_id, partner_code, payload)
),

__expected__int_edge_payload_lines AS (
  SELECT
    v.message_id,
    v.line_index,
    v.line_key,
    v.line_path,
    v.line_kind,
    v.line_sku
  FROM VALUES
    ('PM-1', 0, NULL, '[0]', 'INTEGER', NULL),
    ('PM-1', 1, NULL, '[1]', 'OBJECT', 'MALLARD-01'),
    ('PM-2', 0, NULL, '[0]', 'OBJECT', 'TEAL-02'),
    ('PM-2', 1, NULL, '[1]', 'NULL_VALUE', NULL) AS v(message_id, line_index, line_key, line_path, line_kind, line_sku)
),

__expected__fct_edge_payload_events AS (
  SELECT
    'PM-1' AS message_id,
    'MKT_EU' AS partner_code,
    OBJECT_CONSTRUCT_KEEP_NULL(
      'channel',
      'web',
      'unit_price',
      NULL::FLOAT,
      'amount',
      NULL::NUMBER(18, 2),
      'placed_on',
      NULL::DATE
    )::VARIANT AS event_document,
    '{"amount":null,"channel":"web","placed_on":null,"unit_price":null}' AS event_document_text
  UNION ALL
  SELECT
    'PM-2',
    'GIFTBOX',
    OBJECT_CONSTRUCT_KEEP_NULL(
      'channel',
      NULL::VARCHAR,
      'unit_price',
      NULL::FLOAT,
      'amount',
      NULL::NUMBER(18, 2),
      'placed_on',
      NULL::DATE
    )::VARIANT,
    '{"amount":null,"channel":null,"placed_on":null,"unit_price":null}'
)
