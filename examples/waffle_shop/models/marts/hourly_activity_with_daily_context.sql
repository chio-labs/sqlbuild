MODEL (
  materialized incremental,
  incremental_strategy delete_insert,
  cursor activity_hour,
  cursor_type timestamp,
  cursor_grain hour,
  cursor_inputs (
    daily_activity_rollup activity_day,
  ),
  incremental_mode microbatch,
  batch_size 6h,
  tags [marts, acceptance],
);

SELECT
  h.activity_hour,
  h.orders_placed,
  d.orders_placed AS day_orders_placed,
  h.waffles_ordered,
  h.revenue_cents
FROM __ref("hourly_order_activity") h
INNER JOIN __ref("daily_activity_rollup") d
  ON DATE_TRUNC('day', h.activity_hour) = d.activity_day
