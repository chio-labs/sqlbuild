TEST (name "int_edge_text_payload_skus__groups_and_ranks_by_fields_parsed_from_text");

WITH __ref__stg_edge_partner_payloads AS (
  SELECT
    'PM-1' AS message_id,
    '2026-03-01 09:00:00'::TIMESTAMP_NTZ AS received_at,
    '{"sku": "MALLARD-01", "cart_id": "CART-1"}' AS payload_text
  UNION ALL
  SELECT
    'PM-2',
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ,
    '{"sku": "MALLARD-01", "cart_id": "CART-2"}'
  UNION ALL
  SELECT
    'PM-3',
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ,
    '{"sku": "MALLARD-01", "cart_id": "CART-2"}'
  UNION ALL
  SELECT
    'PM-4',
    '2026-03-01 11:00:00'::TIMESTAMP_NTZ,
    '{"sku": "TEAL-02", "sku": "EIDER-03"}'
  UNION ALL
  SELECT
    'PM-5',
    '2026-03-01 12:00:00'::TIMESTAMP_NTZ,
    'not json'
  UNION ALL
  SELECT
    'PM-6',
    '2026-03-01 08:00:00'::TIMESTAMP_NTZ,
    '{"sku": "TEAL-02"}'
),

__expected__int_edge_text_payload_skus AS (
  SELECT
    'MALLARD-01' AS sku,
    3 AS messages,
    2 AS carts,
    'PM-3' AS latest_message_id
  UNION ALL
  SELECT
    'TEAL-02' AS sku,
    1 AS messages,
    0 AS carts,
    'PM-6' AS latest_message_id
  UNION ALL
  SELECT
    CAST(NULL AS VARCHAR) AS sku,
    2 AS messages,
    0 AS carts,
    'PM-5' AS latest_message_id
)
