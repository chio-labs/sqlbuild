MODEL (
  materialized table,
  tags [marts],
  description "Daily revenue aggregation.",
  audits [
    expression_is_true (
      name "revenue is non-negative",
      expression "total_revenue_cents >= 0",
    ),
  ],
);

SELECT
  CAST(o.ordered_at AS DATE) AS revenue_date,
  COUNT(DISTINCT o.order_id) AS order_count,
  SUM(o.quantity) AS waffles_sold,
  SUM(p.amount_cents) AS total_revenue_cents,
  SUM(p.amount_cents) / COUNT(DISTINCT o.order_id) AS avg_order_value_cents
FROM __ref("stg_orders") o
INNER JOIN __ref("stg_payments") p ON o.order_id = p.order_id AND p.payment_status = 'success'
GROUP BY CAST(o.ordered_at AS DATE)
