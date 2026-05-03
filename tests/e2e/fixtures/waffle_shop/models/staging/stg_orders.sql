MODEL (
  materialized: view,
  tags: ["staging"]
);

SELECT
  id AS order_id,
  customer_id,
  waffle_type_id,
  quantity,
  ordered_at,
  status
FROM __source("raw_orders")
