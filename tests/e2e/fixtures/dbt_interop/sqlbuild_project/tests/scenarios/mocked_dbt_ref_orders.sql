SCENARIO (description: "Mocked dbt ref scenario", tags: ["dbt_ref"]);

WITH
__dbt_ref__fact_orders AS (
  SELECT 10 AS order_id
),
__dbt_ref__analytics__fact_orders AS (
  SELECT 10 AS order_id, 100 AS package_order_id
),
__expected__mocked_dbt_ref_orders AS (
  SELECT 10 AS order_id, 100 AS package_order_id
),
__assert__package_ref_joined AS (
  SELECT *
  FROM __ref("mocked_dbt_ref_orders")
  WHERE package_order_id != 100
)
SELECT 1
