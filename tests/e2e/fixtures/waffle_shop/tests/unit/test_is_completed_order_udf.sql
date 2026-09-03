TEST (mode udf, name "detects_completed_orders");

WITH
input_values AS (
  SELECT 'completed' AS order_status
  UNION ALL
  SELECT 'pending' AS order_status
),
__udf_actual__ AS (
  SELECT
    order_status,
    __udf("is_completed_order")(order_status) AS is_completed_order
  FROM input_values
),
__udf_expected__ AS (
  SELECT 'completed' AS order_status, TRUE AS is_completed_order
  UNION ALL
  SELECT 'pending' AS order_status, FALSE AS is_completed_order
)
SELECT 1
