TEST (name "int_edge_payload_item_totals__totals_and_filters_items_through_typed_lambdas");

WITH __ref__stg_edge_partner_payloads AS (
  SELECT
    'PM-1' AS message_id,
    PARSE_JSON(
      '{"sku": "BUNDLE-01", "items": [{"sku": "MALLARD-01", "qty": 2, "price": 4.995}, '
        || '{"sku": "TEAL-02", "qty": 1, "price": "3.10"}, {"sku": "EIDER-03", "qty": 3}]}'
    ) AS payload
  UNION ALL
  SELECT
    'PM-2',
    PARSE_JSON('{"sku": "BUNDLE-02", "items": []}')
  UNION ALL
  SELECT
    'PM-3',
    PARSE_JSON('{"items": [null, {"sku": null, "qty": 1, "price": 0.1}]}')
  UNION ALL
  SELECT
    'PM-4',
    PARSE_JSON('{"sku": "MALLARD-01"}')
),

__expected__int_edge_payload_item_totals AS (
  SELECT
    'PM-1' AS message_id,
    'BUNDLE-01' AS sku,
    13.10::NUMBER(18, 2) AS item_total,
    PARSE_JSON('[{"price":4.995,"qty":2,"sku":"MALLARD-01"},{"price":"3.10","qty":1,"sku":"TEAL-02"}]')::ARRAY AS priced_items,
    PARSE_JSON('["MALLARD-01","TEAL-02","EIDER-03"]')::ARRAY AS item_skus,
    2 AS priced_item_count
  UNION ALL
  SELECT
    'PM-2' AS message_id,
    'BUNDLE-02' AS sku,
    0.00::NUMBER(18, 2) AS item_total,
    PARSE_JSON('[]')::ARRAY AS priced_items,
    PARSE_JSON('[]')::ARRAY AS item_skus,
    0 AS priced_item_count
  UNION ALL
  SELECT
    'PM-3' AS message_id,
    CAST(NULL AS VARCHAR) AS sku,
    0.10::NUMBER(18, 2) AS item_total,
    PARSE_JSON('[{"price":0.1,"qty":1,"sku":null}]')::ARRAY AS priced_items,
    PARSE_JSON('[undefined,undefined]')::ARRAY AS item_skus,
    1 AS priced_item_count
  UNION ALL
  SELECT
    'PM-4' AS message_id,
    'MALLARD-01' AS sku,
    CAST(NULL AS NUMBER(18, 2)) AS item_total,
    CAST(NULL AS ARRAY) AS priced_items,
    CAST(NULL AS ARRAY) AS item_skus,
    CAST(NULL AS NUMBER(38, 0)) AS priced_item_count
)
