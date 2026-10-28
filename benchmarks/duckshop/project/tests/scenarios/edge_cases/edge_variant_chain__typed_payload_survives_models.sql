SCENARIO (
  description """
    Event documents built from typed SQL values in one model keep each value's type when another
    model reads them back: a FLOAT price, an exact amount, a date and JSON nulls
  """,
  tags ["edge_case"],
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
    ('DL-1', 'PM-1', 'mkt_eu', '{"channel": "web", "amount": 19.99, "placed_on": "2026-03-01"}'),
    ('DL-2', 'PM-2', 'mkt_eu', '{"channel": null, "amount": -0.0}'),
    ('DL-3', 'PM-3', 'giftbox', '{"amount": 0.30000000000000004, "placed_on": "2028-02-28"}') AS v(delivery_id, message_id, partner_code, payload)
),

__expected__fct_edge_payload_events AS (
  SELECT
    v.message_id,
    v.event_document_text
  FROM VALUES
    ('PM-1', '{"amount":19.99,"channel":"web","placed_on":"2026-03-01","unit_price":1.999000000000000e+01}'),
    ('PM-2', '{"amount":0,"channel":null,"placed_on":null,"unit_price":0.000000000000000e+00}'),
    ('PM-3', '{"amount":0.3,"channel":null,"placed_on":"2028-02-28","unit_price":3.000000000000000e-01}') AS v(message_id, event_document_text)
),

__expected__rpt_edge_payload_price_types AS (
  SELECT
    v.message_id,
    v.unit_price_kind,
    v.amount_kind,
    v.placed_on_kind,
    v.channel_kind
  FROM VALUES
    ('PM-1', 'DOUBLE', 'DECIMAL', 'DATE', 'VARCHAR'),
    ('PM-2', 'DOUBLE', 'DECIMAL', 'NULL_VALUE', 'NULL_VALUE'),
    ('PM-3', 'DOUBLE', 'DECIMAL', 'DATE', 'NULL_VALUE') AS v(message_id, unit_price_kind, amount_kind, placed_on_kind, channel_kind)
)
