MODEL (
  materialized view,
  contract enforced,
  columns (
    order_id (type INTEGER),
    customer_id (type INTEGER),
    waffle_type_id (type INTEGER),
    quantity (type INTEGER),
    ordered_at (type TIMESTAMP),
    status (type VARCHAR),
  ),
);

SELECT
  id AS order_id,
  customer_id,
  waffle_type_id,
  quantity,
  ordered_at,
  status
FROM __source("raw__orders")
