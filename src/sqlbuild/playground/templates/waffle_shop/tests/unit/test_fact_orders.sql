TEST();

WITH
__ref__stg_orders AS (
  SELECT
    1 AS order_id,
    100 AS customer_id,
    2 AS waffle_type_id,
    3 AS quantity,
    CAST('2026-04-01 10:00:00' AS TIMESTAMP) AS ordered_at,
    'completed' AS status
),
__ref__stg_payments AS (
  SELECT
    10 AS payment_id,
    1 AS order_id,
    2850 AS amount_cents,
    'card' AS payment_method,
    CAST('2026-04-01 10:05:00' AS TIMESTAMP) AS paid_at,
    'success' AS payment_status
),
__seed__waffle_types AS (
  SELECT
    2 AS waffle_type_id,
    'Liege' AS waffle_name,
    'sweet' AS category,
    950 AS price_cents
),
__expected__fact_orders AS (
  SELECT
    1 AS order_id,
    100 AS customer_id,
    2 AS waffle_type_id,
    'Liege' AS waffle_name,
    'sweet' AS waffle_category,
    3 AS quantity,
    2850 AS line_total_cents,
    CAST('2026-04-01 10:00:00' AS TIMESTAMP) AS ordered_at,
    'completed' AS order_status,
    TRUE AS is_completed_order,
    'card' AS payment_method,
    'success' AS payment_status,
    2850 AS payment_amount_cents
),
__assert__line_totals_are_non_negative AS (
  SELECT *
  FROM __ref("fact_orders")
  WHERE line_total_cents < 0
)
SELECT 1
