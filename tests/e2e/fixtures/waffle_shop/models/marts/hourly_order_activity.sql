MODEL (
  materialized: incremental,
  incremental_strategy: delete_insert,
  cursor: "activity_hour",
  cursor_type: timestamp,
  cursor_grain: hour,
  cursor_inputs: {
    fact_orders: "ordered_at"
  },
  incremental_mode: microbatch,
  batch_size: "1d",
  tags: ["marts"]
);

SELECT
  DATE_TRUNC('hour', o.ordered_at) AS activity_hour,
  COUNT(*) AS orders_placed,
  SUM(o.quantity) AS waffles_ordered,
  SUM(o.line_total_cents) AS revenue_cents
FROM __ref("fact_orders") o
GROUP BY DATE_TRUNC('hour', o.ordered_at)
