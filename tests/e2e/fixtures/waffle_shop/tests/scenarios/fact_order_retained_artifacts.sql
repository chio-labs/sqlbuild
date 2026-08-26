SCENARIO (
  description "Retained scenario artifacts include source ref seed and model relations",
  tags ["retention", "example"]
);

WITH
__source__raw_orders AS (
  SELECT
    101 AS id,
    501 AS customer_id,
    1 AS waffle_type_id,
    2 AS quantity,
    CAST('2026-04-05 08:30:00' AS TIMESTAMP) AS ordered_at,
    'completed' AS status
),

__ref__stg_payments AS (
  SELECT
    201 AS payment_id,
    101 AS order_id,
    1700 AS amount_cents,
    'credit_card' AS payment_method,
    CAST('2026-04-05 08:31:00' AS TIMESTAMP) AS paid_at,
    'success' AS payment_status
),

__seed__waffle_types AS (
  SELECT
    1 AS waffle_type_id,
    'Classic Belgian' AS waffle_name,
    'sweet' AS category,
    850 AS price_cents
),

__expected__scenario_order_prices AS (
  SELECT
    101 AS order_id,
    2 AS quantity,
    'Classic Belgian' AS waffle_name,
    850 AS price_cents,
    1700 AS line_total_cents,
    1700 AS payment_amount_cents
),

__assert__positive_line_total AS (
  SELECT *
  FROM __ref("scenario_order_prices")
  WHERE line_total_cents <= 0
)

SELECT 1
