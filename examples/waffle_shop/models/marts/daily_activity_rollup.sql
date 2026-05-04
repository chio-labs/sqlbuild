MODEL (
  materialized incremental,
  incremental_strategy delete_insert,
  cursor activity_day,
  cursor_type timestamp,
  cursor_grain day,
  cursor_inputs (
    hourly_order_activity activity_hour,
  ),
  incremental_mode microbatch,
  batch_size 2d,
  query_change_backfill bounded-14d,
  tags [marts, acceptance],
);

SELECT
  @timestamp_trunc('day', 'activity_hour') AS activity_day,
  SUM(orders_placed) AS orders_placed,
  SUM(waffles_ordered) AS waffles_ordered,
  SUM(revenue_cents) AS revenue_cents
FROM __ref("hourly_order_activity")
GROUP BY @timestamp_trunc('day', 'activity_hour')
