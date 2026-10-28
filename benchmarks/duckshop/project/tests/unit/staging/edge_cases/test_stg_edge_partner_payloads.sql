TEST (name "stg_edge_partner_payloads__keeps_latest_delivery_of_each_message");

WITH __source__edge__partner_payloads AS (
  SELECT
    'D1' AS delivery_id,
    'PM-1' AS message_id,
    ' mkt_eu ' AS partner_code,
    NULL AS received_at,
    PARSE_JSON('{"sku": "MALLARD-01"}') AS payload,
    NULL AS payload_text,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'D2',
    'PM-1',
    'mkt_eu',
    NULL,
    PARSE_JSON('{"sku": "TEAL-02"}'),
    NULL,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'D3',
    'PM-2',
    NULL,
    NULL,
    PARSE_JSON('{"sku": "EIDER-03"}'),
    NULL,
    '2026-03-02 09:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'D0',
    'PM-2',
    'giftbox',
    NULL,
    PARSE_JSON('{"sku": "PINTAIL-04"}'),
    NULL,
    '2026-03-01 09:00:00'::TIMESTAMP_NTZ
),

__expected__stg_edge_partner_payloads AS (
  SELECT
    'PM-1' AS message_id,
    'MKT_EU' AS partner_code,
    PARSE_JSON('{"sku":"TEAL-02"}') AS payload
  UNION ALL
  SELECT
    'PM-2' AS message_id,
    CAST(NULL AS VARCHAR) AS partner_code,
    PARSE_JSON('{"sku":"EIDER-03"}') AS payload
)

TEST (name "stg_edge_partner_payloads__parses_lenient_and_malformed_message_text");

WITH __source__edge__partner_payloads AS (
  SELECT
    'D1' AS delivery_id,
    'PM-1' AS message_id,
    NULL AS partner_code,
    NULL AS received_at,
    NULL AS payload,
    '{"sku": "MALLARD-01", "sku": "TEAL-02"}' AS payload_text,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'D2',
    'PM-2',
    NULL,
    NULL,
    NULL,
    '{''sku'': ''TEAL-02''}',
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'D3',
    'PM-3',
    NULL,
    NULL,
    NULL,
    '{"weight_kg": NaN}',
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'D4',
    'PM-4',
    NULL,
    NULL,
    NULL,
    '{"lines": [1, 2,]}',
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'D5',
    'PM-5',
    NULL,
    NULL,
    NULL,
    '"{\\"orderId\\": \\"DS-O-1001\\"}"',
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'D7',
    'PM-7',
    NULL,
    NULL,
    NULL,
    '{"gift": undefined}',
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'D8',
    'PM-8',
    NULL,
    NULL,
    NULL,
    '',
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'D9',
    'PM-9',
    NULL,
    NULL,
    NULL,
    'null',
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'D10',
    'PM-10',
    NULL,
    NULL,
    NULL,
    '{"Sku": "EIDER-03", "sku": "PINTAIL-04"}',
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_edge_partner_payloads AS (
  SELECT
    'PM-1' AS message_id,
    CAST(NULL AS VARIANT) AS text_payload
  UNION ALL
  SELECT
    'PM-10' AS message_id,
    PARSE_JSON('{"Sku":"EIDER-03","sku":"PINTAIL-04"}') AS text_payload
  UNION ALL
  SELECT
    'PM-2' AS message_id,
    PARSE_JSON('{"sku":"TEAL-02"}') AS text_payload
  UNION ALL
  SELECT
    'PM-3' AS message_id,
    PARSE_JSON('{"weight_kg":NaN}') AS text_payload
  UNION ALL
  SELECT
    'PM-4' AS message_id,
    PARSE_JSON('{"lines":[1,2,undefined]}') AS text_payload
  UNION ALL
  SELECT
    'PM-5' AS message_id,
    PARSE_JSON('"{\\"orderId\\": \\"DS-O-1001\\"}"') AS text_payload
  UNION ALL
  SELECT
    'PM-7' AS message_id,
    PARSE_JSON('{"gift":null}') AS text_payload
  UNION ALL
  SELECT
    'PM-8' AS message_id,
    CAST(NULL AS VARIANT) AS text_payload
  UNION ALL
  SELECT
    'PM-9' AS message_id,
    PARSE_JSON('null') AS text_payload
)

TEST (name "stg_edge_partner_payloads__reads_quantities_by_json_number_kind");

WITH __source__edge__partner_payloads AS (
  SELECT
    'D1' AS delivery_id,
    'PM-1' AS message_id,
    NULL AS partner_code,
    NULL AS received_at,
    PARSE_JSON('{"qty": 2}') AS payload,
    NULL AS payload_text,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'D2',
    'PM-2',
    NULL,
    NULL,
    PARSE_JSON('{"qty": 2.0}'),
    NULL,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'D3',
    'PM-3',
    NULL,
    NULL,
    PARSE_JSON('{"qty": "2"}'),
    NULL,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'D4',
    'PM-4',
    NULL,
    NULL,
    PARSE_JSON('{"qty": 2e0}'),
    NULL,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'D5',
    'PM-5',
    NULL,
    NULL,
    PARSE_JSON('{"qty": 2.5}'),
    NULL,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'D6',
    'PM-6',
    NULL,
    NULL,
    PARSE_JSON('{"qty": "2.5"}'),
    NULL,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'D7',
    'PM-7',
    NULL,
    NULL,
    PARSE_JSON('{"qty": -2.5}'),
    NULL,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'D8',
    'PM-8',
    NULL,
    NULL,
    PARSE_JSON('{"qty": true}'),
    NULL,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'D9',
    'PM-9',
    NULL,
    NULL,
    PARSE_JSON('{"qty": null}'),
    NULL,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'D10',
    'PM-10',
    NULL,
    NULL,
    PARSE_JSON('{}'),
    NULL,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_edge_partner_payloads AS (
  SELECT
    'PM-1' AS message_id,
    'INTEGER' AS qty_kind,
    TRUE AS qty_is_integer,
    TRUE AS qty_is_decimal,
    TRUE AS qty_is_double,
    2 AS qty_units,
    2.00::NUMBER(18, 2) AS qty_text_units
  UNION ALL
  SELECT
    'PM-10' AS message_id,
    CAST(NULL AS VARCHAR) AS qty_kind,
    CAST(NULL AS BOOLEAN) AS qty_is_integer,
    CAST(NULL AS BOOLEAN) AS qty_is_decimal,
    CAST(NULL AS BOOLEAN) AS qty_is_double,
    CAST(NULL AS NUMBER(18, 0)) AS qty_units,
    CAST(NULL AS NUMBER(18, 2)) AS qty_text_units
  UNION ALL
  SELECT
    'PM-2' AS message_id,
    'INTEGER' AS qty_kind,
    TRUE AS qty_is_integer,
    TRUE AS qty_is_decimal,
    TRUE AS qty_is_double,
    2 AS qty_units,
    2.00::NUMBER(18, 2) AS qty_text_units
  UNION ALL
  SELECT
    'PM-3' AS message_id,
    'VARCHAR' AS qty_kind,
    FALSE AS qty_is_integer,
    FALSE AS qty_is_decimal,
    FALSE AS qty_is_double,
    2 AS qty_units,
    2.00::NUMBER(18, 2) AS qty_text_units
  UNION ALL
  SELECT
    'PM-4' AS message_id,
    'DOUBLE' AS qty_kind,
    FALSE AS qty_is_integer,
    FALSE AS qty_is_decimal,
    TRUE AS qty_is_double,
    2 AS qty_units,
    2.00::NUMBER(18, 2) AS qty_text_units
  UNION ALL
  SELECT
    'PM-5' AS message_id,
    'DECIMAL' AS qty_kind,
    FALSE AS qty_is_integer,
    TRUE AS qty_is_decimal,
    TRUE AS qty_is_double,
    3 AS qty_units,
    2.50::NUMBER(18, 2) AS qty_text_units
  UNION ALL
  SELECT
    'PM-6' AS message_id,
    'VARCHAR' AS qty_kind,
    FALSE AS qty_is_integer,
    FALSE AS qty_is_decimal,
    FALSE AS qty_is_double,
    3 AS qty_units,
    2.50::NUMBER(18, 2) AS qty_text_units
  UNION ALL
  SELECT
    'PM-7' AS message_id,
    'DECIMAL' AS qty_kind,
    FALSE AS qty_is_integer,
    TRUE AS qty_is_decimal,
    TRUE AS qty_is_double,
    -3 AS qty_units,
    -2.50::NUMBER(18, 2) AS qty_text_units
  UNION ALL
  SELECT
    'PM-8' AS message_id,
    'BOOLEAN' AS qty_kind,
    FALSE AS qty_is_integer,
    FALSE AS qty_is_decimal,
    FALSE AS qty_is_double,
    1 AS qty_units,
    CAST(NULL AS NUMBER(18, 2)) AS qty_text_units
  UNION ALL
  SELECT
    'PM-9' AS message_id,
    'NULL_VALUE' AS qty_kind,
    FALSE AS qty_is_integer,
    FALSE AS qty_is_decimal,
    FALSE AS qty_is_double,
    CAST(NULL AS NUMBER(18, 0)) AS qty_units,
    CAST(NULL AS NUMBER(18, 2)) AS qty_text_units
)

TEST (name "stg_edge_partner_payloads__casts_amounts_flags_and_dates_out_of_json");

WITH __source__edge__partner_payloads AS (
  SELECT
    'D1' AS delivery_id,
    'PM-1' AS message_id,
    NULL AS partner_code,
    NULL AS received_at,
    PARSE_JSON('{"amount": 1.50, "gift": "yes", "placed_on": "2026-03-01"}') AS payload,
    NULL AS payload_text,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'D2',
    'PM-2',
    NULL,
    NULL,
    PARSE_JSON('{"amount": 1E+3, "gift": true, "placed_on": "2026-02-28T23:30:00"}'),
    NULL,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'D3',
    'PM-3',
    NULL,
    NULL,
    PARSE_JSON('{"amount": 2.345, "gift": "on", "placed_on": "2026-03-01"}'),
    NULL,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'D4',
    'PM-4',
    NULL,
    NULL,
    PARSE_JSON('{"amount": -0, "gift": "N", "placed_on": null}'),
    NULL,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'D5',
    'PM-5',
    NULL,
    NULL,
    PARSE_JSON('{"amount": "7.125", "gift": "false"}'),
    NULL,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'D6',
    'PM-6',
    NULL,
    NULL,
    PARSE_JSON('{"amount": 1e-7, "gift": "0"}'),
    NULL,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_edge_partner_payloads AS (
  SELECT
    'PM-1' AS message_id,
    1.50::NUMBER(18, 2) AS amount,
    '1.5'::FLOAT AS amount_float,
    '1.5' AS amount_text,
    TRUE AS is_gift,
    '2026-03-01'::DATE AS placed_on
  UNION ALL
  SELECT
    'PM-2' AS message_id,
    1000.00::NUMBER(18, 2) AS amount,
    '1000.0'::FLOAT AS amount_float,
    '1000' AS amount_text,
    TRUE AS is_gift,
    '2026-02-28'::DATE AS placed_on
  UNION ALL
  SELECT
    'PM-3' AS message_id,
    2.35::NUMBER(18, 2) AS amount,
    '2.345'::FLOAT AS amount_float,
    '2.345' AS amount_text,
    TRUE AS is_gift,
    '2026-03-01'::DATE AS placed_on
  UNION ALL
  SELECT
    'PM-4' AS message_id,
    0.00::NUMBER(18, 2) AS amount,
    '0.0'::FLOAT AS amount_float,
    '0' AS amount_text,
    FALSE AS is_gift,
    CAST(NULL AS DATE) AS placed_on
  UNION ALL
  SELECT
    'PM-5' AS message_id,
    7.13::NUMBER(18, 2) AS amount,
    '7.125'::FLOAT AS amount_float,
    '7.125' AS amount_text,
    FALSE AS is_gift,
    CAST(NULL AS DATE) AS placed_on
  UNION ALL
  SELECT
    'PM-6' AS message_id,
    0.00::NUMBER(18, 2) AS amount,
    '1e-07'::FLOAT AS amount_float,
    '1e-07' AS amount_text,
    FALSE AS is_gift,
    CAST(NULL AS DATE) AS placed_on
)

TEST (name "stg_edge_partner_payloads__keeps_long_json_numbers_exact");

WITH __source__edge__partner_payloads AS (
  SELECT
    'D1' AS delivery_id,
    'PM-1' AS message_id,
    NULL AS partner_code,
    NULL AS received_at,
    PARSE_JSON('{"amount": 19.990000000000002, "txn_id": 12345678901234567890}') AS payload,
    NULL AS payload_text,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'D2',
    'PM-2',
    NULL,
    NULL,
    PARSE_JSON('{"amount": 0.1, "txn_id": 9007199254740993}'),
    NULL,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'D3',
    'PM-3',
    NULL,
    NULL,
    PARSE_JSON('{"amount": 1234567890123456.25, "txn_id": "00042"}'),
    NULL,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_edge_partner_payloads AS (
  SELECT
    'PM-1' AS message_id,
    19.99::NUMBER(18, 2) AS amount,
    '19.990000000000002'::FLOAT AS amount_float,
    '19.990000000000002' AS amount_text,
    '12345678901234567890' AS transaction_id_text,
    12345678901234567890 AS transaction_id
  UNION ALL
  SELECT
    'PM-2' AS message_id,
    0.10::NUMBER(18, 2) AS amount,
    '0.1'::FLOAT AS amount_float,
    '0.1' AS amount_text,
    '9007199254740993' AS transaction_id_text,
    9007199254740993 AS transaction_id
  UNION ALL
  SELECT
    'PM-3' AS message_id,
    1234567890123456.25::NUMBER(18, 2) AS amount,
    '1234567890123456.2'::FLOAT AS amount_float,
    '1234567890123456.25' AS amount_text,
    '00042' AS transaction_id_text,
    42 AS transaction_id
)

TEST (name "stg_edge_partner_payloads__reads_first_and_last_items_of_any_length");

WITH __source__edge__partner_payloads AS (
  SELECT
    'D1' AS delivery_id,
    'PM-1' AS message_id,
    NULL AS partner_code,
    NULL AS received_at,
    PARSE_JSON('{"items": []}') AS payload,
    NULL AS payload_text,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'D2',
    'PM-2',
    NULL,
    NULL,
    PARSE_JSON('{"items": [{"sku": "MALLARD-01"}]}'),
    NULL,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'D3',
    'PM-3',
    NULL,
    NULL,
    PARSE_JSON('{"items": [{"sku": "MALLARD-01"}, {"SKU": "TEAL-02"}, {"sku": "EIDER-03"}]}'),
    NULL,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'D4',
    'PM-4',
    NULL,
    NULL,
    PARSE_JSON('{"items": null}'),
    NULL,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'D5',
    'PM-5',
    NULL,
    NULL,
    PARSE_JSON('{}'),
    NULL,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'D6',
    'PM-6',
    NULL,
    NULL,
    PARSE_JSON('{"items": [null, {"sku": "PINTAIL-04"}]}'),
    NULL,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_edge_partner_payloads AS (
  SELECT
    'PM-1' AS message_id,
    CAST(NULL AS VARCHAR) AS first_item_sku,
    CAST(NULL AS VARCHAR) AS last_item_sku,
    0 AS item_count
  UNION ALL
  SELECT
    'PM-2' AS message_id,
    'MALLARD-01' AS first_item_sku,
    'MALLARD-01' AS last_item_sku,
    1 AS item_count
  UNION ALL
  SELECT
    'PM-3' AS message_id,
    'MALLARD-01' AS first_item_sku,
    'EIDER-03' AS last_item_sku,
    3 AS item_count
  UNION ALL
  SELECT
    'PM-4' AS message_id,
    CAST(NULL AS VARCHAR) AS first_item_sku,
    CAST(NULL AS VARCHAR) AS last_item_sku,
    CAST(NULL AS NUMBER(38, 0)) AS item_count
  UNION ALL
  SELECT
    'PM-5' AS message_id,
    CAST(NULL AS VARCHAR) AS first_item_sku,
    CAST(NULL AS VARCHAR) AS last_item_sku,
    CAST(NULL AS NUMBER(38, 0)) AS item_count
  UNION ALL
  SELECT
    'PM-6' AS message_id,
    CAST(NULL AS VARCHAR) AS first_item_sku,
    'PINTAIL-04' AS last_item_sku,
    2 AS item_count
)
