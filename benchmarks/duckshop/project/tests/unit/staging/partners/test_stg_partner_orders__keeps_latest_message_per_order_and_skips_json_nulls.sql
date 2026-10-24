TEST (name "stg_partner_orders__keeps_latest_message_per_order_and_skips_json_nulls");

WITH __source__partners__partner_orders AS (
  SELECT
    'MS1' AS message_id,
    'mkt' AS partner_code,
    1 AS schema_version,
    '2026-03-10 10:00:00'::TIMESTAMP_NTZ AS received_at,
    PARSE_JSON('{"orderId": "A1"}')::VARIANT AS payload,
    '2026-03-10 12:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'MS2',
    'mkt',
    1,
    '2026-03-10 11:00:00'::TIMESTAMP_NTZ,
    PARSE_JSON('{"orderId": "A1", "status": "paid"}')::VARIANT,
    '2026-03-10 12:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'MS3',
    'mkt',
    2,
    '2026-03-10 11:00:00'::TIMESTAMP_NTZ,
    PARSE_JSON('{"order": {"id": "B7"}}')::VARIANT,
    '2026-03-10 11:30:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'MS3',
    'mkt',
    2,
    '2026-03-10 11:00:00'::TIMESTAMP_NTZ,
    PARSE_JSON('{"order": {"id": "B7"}, "v": 2}')::VARIANT,
    '2026-03-10 12:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'MS4',
    'mkt',
    2,
    '2026-03-10 12:00:00'::TIMESTAMP_NTZ,
    PARSE_JSON('{"orderId": null, "order": {"id": "C9"}}')::VARIANT,
    '2026-03-10 12:00:00'::TIMESTAMP_NTZ
),

__expected__stg_partner_orders AS (
  SELECT
    'MS2' AS message_id,
    'MKT' AS partner_code,
    1 AS schema_version,
    'A1' AS external_order_id
  UNION ALL
  SELECT
    'MS3' AS message_id,
    'MKT' AS partner_code,
    2 AS schema_version,
    'B7' AS external_order_id
  UNION ALL
  SELECT
    'MS4' AS message_id,
    'MKT' AS partner_code,
    2 AS schema_version,
    'C9' AS external_order_id
)
