MODEL (
  materialized incremental,
  incremental_strategy delete_insert,
  cursor activity_hour,
  cursor_type timestamp,
  cursor_grain hour,
  cursor_inputs (
    fact_orders ordered_at,
  ),
  incremental_mode microbatch,
  batch_size 1d,
  tags [marts],
  description "Hourly order activity aggregated via microbatch incremental.",
  columns (
    activity_hour (audits [not_null (run_scope delta_and_final)]),
  ),
  audits [
    expression_is_true (
      name "orders placed is non-negative",
      expression "orders_placed >= 0",
      run_scope delta_and_final,
    ),
  ],
);

SELECT
  @timestamp_trunc('hour', 'o.ordered_at') AS activity_hour,
  COUNT(*) AS orders_placed,
  SUM(o.quantity) AS waffles_ordered,
  SUM(o.line_total_cents) AS revenue_cents
FROM __ref("fact_orders") o
GROUP BY @timestamp_trunc('hour', 'o.ordered_at')
