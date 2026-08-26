SCENARIO (
  description "Daily revenue aggregates multiple successful orders",
  tags ["revenue", "example"]
);

WITH
__ref__stg_orders AS (
  SELECT
    11 AS order_id,
    20 AS customer_id,
    1 AS waffle_type_id,
    1 AS quantity,
    CAST('2026-04-02 08:30:00' AS TIMESTAMP) AS ordered_at,
    'completed' AS status
  UNION ALL
  SELECT
    12 AS order_id,
    21 AS customer_id,
    3 AS waffle_type_id,
    3 AS quantity,
    CAST('2026-04-02 12:15:00' AS TIMESTAMP) AS ordered_at,
    'completed' AS status
),

__ref__stg_payments AS (
  SELECT
    11 AS payment_id,
    11 AS order_id,
    850 AS amount_cents,
    'cash' AS payment_method,
    CAST('2026-04-02 08:31:00' AS TIMESTAMP) AS paid_at,
    'success' AS payment_status
  UNION ALL
  SELECT
    12 AS payment_id,
    12 AS order_id,
    2250 AS amount_cents,
    'debit_card' AS payment_method,
    CAST('2026-04-02 12:16:00' AS TIMESTAMP) AS paid_at,
    'success' AS payment_status
),

__expected__daily_revenue AS (
  SELECT
    CAST('2026-04-02' AS DATE) AS revenue_date,
    2 AS order_count,
    4 AS waffles_sold,
    3100 AS total_revenue_cents,
    1550 AS avg_order_value_cents
),

__assert__positive_average_order_value AS (
  SELECT *
  FROM __ref("daily_revenue")
  WHERE avg_order_value_cents <= 0
)

SELECT 1
