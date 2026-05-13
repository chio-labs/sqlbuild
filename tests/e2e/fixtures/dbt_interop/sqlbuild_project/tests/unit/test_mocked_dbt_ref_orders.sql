TEST();

WITH
__dbt_ref__fact_orders AS (
  SELECT 10 AS order_id
),
__dbt_ref__analytics__fact_orders AS (
  SELECT 10 AS order_id, 100 AS package_order_id
),
__expected__mocked_dbt_ref_orders AS (
  SELECT 10 AS order_id, 100 AS package_order_id
)
SELECT 1
