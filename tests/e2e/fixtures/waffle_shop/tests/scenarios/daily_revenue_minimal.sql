SCENARIO (
  description: "Daily revenue includes only successful payments",
  tags: ["revenue", "example"]
);

WITH
__ref__stg_orders AS (
  SELECT
    1 AS order_id,
    1 AS customer_id,
    1 AS waffle_type_id,
    2 AS quantity,
    CAST('2026-04-01 09:15:00' AS TIMESTAMP) AS ordered_at,
    'completed' AS status
),

__ref__stg_payments AS (
  SELECT
    id AS payment_id,
    order_id,
    amount_cents,
    payment_method,
    paid_at,
    status AS payment_status
  FROM __source("raw_payments")
  WHERE id = 1
),

__expected__daily_revenue AS (
  SELECT
    CAST('2026-04-01' AS DATE) AS revenue_date,
    1 AS order_count,
    2 AS waffles_sold,
    1700 AS total_revenue_cents,
    1700 AS avg_order_value_cents
),

__assert__no_negative_revenue AS (
  SELECT *
  FROM __ref("daily_revenue")
  WHERE total_revenue_cents < 0
)

SELECT 1
