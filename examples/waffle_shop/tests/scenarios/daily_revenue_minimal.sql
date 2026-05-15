SCENARIO (
  description: "Daily revenue includes only successful payments",
  tags: ["revenue", "example"]
);

WITH
__ref__stg_orders AS (
  SELECT
    id AS order_id,
    customer_id,
    waffle_type_id,
    quantity,
    ordered_at,
    status
  FROM __source("raw_orders")
  WHERE id = 1
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
    17.0 AS total_revenue_dollars,
    1700 AS avg_order_value_cents
),

__assert__no_negative_revenue AS (
  SELECT *
  FROM __ref("daily_revenue")
  WHERE total_revenue_cents < 0
)

SELECT 1
