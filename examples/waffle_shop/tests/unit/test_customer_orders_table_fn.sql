TEST (mode: table_fn, name: "returns customer orders");

WITH
__table_fn_actual__ AS (
  SELECT
    order_id,
    order_status,
    is_completed_order
  FROM __table_fn("customer_orders")(1)
),
__table_fn_expected__ AS (
  SELECT 1 AS order_id, 'completed' AS order_status, TRUE AS is_completed_order
  UNION ALL
  SELECT 2 AS order_id, 'completed' AS order_status, TRUE AS is_completed_order
  UNION ALL
  SELECT 8 AS order_id, 'completed' AS order_status, TRUE AS is_completed_order
)
SELECT 1
