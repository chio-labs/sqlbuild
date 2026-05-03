MODEL (
  materialized view,
  tags [staging],
);

SELECT
  id AS payment_id,
  order_id,
  amount_cents,
  payment_method,
  paid_at,
  status AS payment_status
FROM __source("raw_payments")
