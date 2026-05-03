TEST();

WITH
__source__raw_orders AS (
  SELECT
    1 AS id,
    100 AS customer_id,
    2 AS waffle_type_id,
    3 AS quantity,
    '2026-04-01 10:00:00' AS ordered_at,
    'completed' AS status
  UNION ALL
  SELECT
    2 AS id,
    101 AS customer_id,
    1 AS waffle_type_id,
    1 AS quantity,
    '2026-04-01 11:00:00' AS ordered_at,
    'completed' AS status
),
__source__raw_payments AS (
  SELECT
    10 AS id,
    1 AS order_id,
    2850 AS amount_cents,
    'card' AS payment_method,
    '2026-04-01 10:05:00' AS paid_at,
    'success' AS status
  UNION ALL
  SELECT
    11 AS id,
    2 AS order_id,
    850 AS amount_cents,
    'cash' AS payment_method,
    '2026-04-01 11:10:00' AS paid_at,
    'failed' AS status
),
__expected__stg_orders AS (
  SELECT
    1 AS order_id,
    100 AS customer_id,
    2 AS waffle_type_id,
    3 AS quantity,
    '2026-04-01 10:00:00' AS ordered_at,
    'completed' AS status
  UNION ALL
  SELECT
    2 AS order_id,
    101 AS customer_id,
    1 AS waffle_type_id,
    1 AS quantity,
    '2026-04-01 11:00:00' AS ordered_at,
    'completed' AS status
),
__expected__stg_payments AS (
  SELECT
    10 AS payment_id,
    1 AS order_id,
    2850 AS amount_cents,
    'card' AS payment_method,
    '2026-04-01 10:05:00' AS paid_at,
    'success' AS payment_status
  UNION ALL
  SELECT
    11 AS payment_id,
    2 AS order_id,
    850 AS amount_cents,
    'cash' AS payment_method,
    '2026-04-01 11:10:00' AS paid_at,
    'failed' AS payment_status
),
__expected__daily_revenue AS (
  SELECT
    CAST('2026-04-01' AS DATE) AS revenue_date,
    1 AS order_count,
    3 AS waffles_sold,
    2850 AS total_revenue_cents,
    28.5 AS total_revenue_dollars,
    2850 AS avg_order_value_cents
)
SELECT 1
