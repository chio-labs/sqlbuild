TEST();

WITH
__source__raw_orders AS (
  SELECT
    1 AS id,
    100 AS customer_id,
    2 AS waffle_type_id,
    3 AS quantity,
    CAST('2026-04-01 10:00:00' AS TIMESTAMP) AS ordered_at,
    'completed' AS status
),
__expected__stg_orders AS (
  SELECT
    1 AS order_id,
    100 AS customer_id,
    2 AS waffle_type_id,
    3 AS quantity,
    CAST('2026-04-01 10:00:00' AS TIMESTAMP) AS ordered_at,
    'completed' AS status
)
SELECT 1
