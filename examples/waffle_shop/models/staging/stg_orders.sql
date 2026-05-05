MODEL (
  materialized view,
  tags [staging],
  description "Cleaned order records.",
  columns (
    order_id (audits [not_null, unique]),
    customer_id (audits [not_null]),
    status (
      audits [
        accepted_values (values ["placed", "preparing", "ready", "completed", "cancelled"]),
      ],
    ),
  ),
);

SELECT
  id AS order_id,
  customer_id,
  waffle_type_id,
  quantity,
  ordered_at,
  status
FROM __source("raw_orders")
