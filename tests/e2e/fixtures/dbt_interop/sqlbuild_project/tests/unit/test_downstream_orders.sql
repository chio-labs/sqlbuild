TEST();

WITH
__dbt_ref__analytics__fact_orders AS (
  SELECT 1 AS order_id
),
__ref__downstream_orders AS (
  SELECT 1 AS order_id
),
__expected__downstream_orders AS (
  SELECT 1 AS order_id
)
SELECT 1
