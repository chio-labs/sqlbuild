TEST (name "rpt_edge_payload_price_types__reads_typed_values_back_out_of_event_documents");

WITH __ref__fct_edge_payload_events AS (
  SELECT
    v.message_id,
    NULL AS partner_code,
    OBJECT_CONSTRUCT_KEEP_NULL(
      'channel',
      v.channel,
      'unit_price',
      v.unit_price::FLOAT,
      'amount',
      v.amount::NUMBER(18, 2),
      'placed_on',
      v.placed_on::DATE
    )::VARIANT AS event_document
  FROM VALUES
    ('PM-1', 'web', 19.99, 19.99, '2026-03-01'),
    ('PM-2', NULL, -0.0, 0, NULL),
    ('PM-3', 'app', 0.30000000000000004, 1234.5, '2028-02-28') AS v(message_id, channel, unit_price, amount, placed_on)
),

__expected__rpt_edge_payload_price_types AS (
  SELECT
    'PM-1' AS message_id,
    'DOUBLE' AS unit_price_kind,
    '19.99'::FLOAT AS unit_price,
    'DECIMAL' AS amount_kind,
    19.99::NUMBER(18, 2) AS amount,
    'DATE' AS placed_on_kind,
    '2026-03-01'::DATE AS placed_on,
    '2026-03-01' AS placed_on_text,
    'VARCHAR' AS channel_kind
  UNION ALL
  SELECT
    'PM-2' AS message_id,
    'DOUBLE' AS unit_price_kind,
    '0.0'::FLOAT AS unit_price,
    'DECIMAL' AS amount_kind,
    0.00::NUMBER(18, 2) AS amount,
    'NULL_VALUE' AS placed_on_kind,
    CAST(NULL AS DATE) AS placed_on,
    CAST(NULL AS VARCHAR) AS placed_on_text,
    'NULL_VALUE' AS channel_kind
  UNION ALL
  SELECT
    'PM-3' AS message_id,
    'DOUBLE' AS unit_price_kind,
    '0.30000000000000004'::FLOAT AS unit_price,
    'DECIMAL' AS amount_kind,
    1234.50::NUMBER(18, 2) AS amount,
    'DATE' AS placed_on_kind,
    '2028-02-28'::DATE AS placed_on,
    '2028-02-28' AS placed_on_text,
    'VARCHAR' AS channel_kind
)
