MODEL (
  materialized incremental,
  incremental_strategy delete_insert,
  cursor activity_day,
  cursor_type timestamp,
  cursor_grain day,
  cursor_filter_inputs (
    hourly_order_activity activity_hour,
  ),
  incremental_mode microbatch,
  batch_size 2d,
  replay_on_change bounded-14d,
  tags [marts, acceptance],
  description "Downstream daily microbatch rollup with a wider batch size than its hourly upstream.",
  columns (
    activity_day (audits [not_null (run_scope delta_and_final)]),
  ),
  audits [
    expression_is_true (
      name "daily orders placed is non-negative",
      expression "orders_placed >= 0",
      run_scope delta_and_final,
    ),
  ],
);

SELECT
  @timestamp_trunc('day', 'activity_hour') AS activity_day,
  SUM(orders_placed) AS orders_placed,
  SUM(waffles_ordered) AS waffles_ordered,
  SUM(revenue_cents) AS revenue_cents
FROM __ref("hourly_order_activity")
GROUP BY @timestamp_trunc('day', 'activity_hour')
