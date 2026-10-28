TEST (name "fct_edge_payload_events__publishes_event_documents_from_typed_values");

WITH __ref__stg_edge_partner_payloads AS (
  SELECT
    'PM-1' AS message_id,
    'MKT_EU' AS partner_code,
    PARSE_JSON('{"channel": "web"}') AS payload,
    19.99::FLOAT AS amount_float,
    19.99::NUMBER(18, 2) AS amount,
    '2026-03-01'::DATE AS placed_on
  UNION ALL
  SELECT
    'PM-2',
    'MKT_EU',
    PARSE_JSON('{"channel": null}'),
    -0.0::FLOAT,
    0.00::NUMBER(18, 2),
    NULL
  UNION ALL
  SELECT
    'PM-3',
    'GIFTBOX',
    PARSE_JSON('{}'),
    0.1::FLOAT + 0.2::FLOAT,
    1234.50::NUMBER(18, 2),
    '2028-02-29'::DATE - 1
),

__expected__fct_edge_payload_events AS (
  SELECT
    'PM-1' AS message_id,
    '{"amount":19.99,"channel":"web","placed_on":"2026-03-01","unit_price":1.999000000000000e+01}' AS event_document_text
  UNION ALL
  SELECT
    'PM-2' AS message_id,
    '{"amount":0,"channel":null,"placed_on":null,"unit_price":-0.000000000000000e+00}' AS event_document_text
  UNION ALL
  SELECT
    'PM-3' AS message_id,
    '{"amount":1234.5,"channel":null,"placed_on":"2028-02-28","unit_price":3.000000000000000e-01}' AS event_document_text
)
