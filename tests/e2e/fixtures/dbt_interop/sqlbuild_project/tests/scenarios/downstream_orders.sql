SCENARIO (description "Mocked dbt ref scenario", tags ["dbt_ref"]);

WITH
__dbt_ref__analytics__fact_orders AS (
  SELECT 1 AS order_id
),
__expected__downstream_orders AS (
  SELECT 1 AS order_id
),
__assert__downstream_joined AS (
  SELECT *
  FROM __ref("downstream_orders")
  WHERE order_id != 1
)
SELECT 1
