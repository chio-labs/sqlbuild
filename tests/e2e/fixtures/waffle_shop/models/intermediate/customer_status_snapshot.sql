MODEL (
  materialized: incremental,
  incremental_strategy: merge,
  unique_key: ["customer_id"],
  cursor: "last_ordered_at",
  cursor_type: timestamp,
  cursor_grain: second,
  cursor_inputs: {
    fact_orders: "ordered_at"
  },
  query_change_backfill: "full",
  on_schema_change: sync_all_columns,
  schema_change_backfill:
    add_column: "bounded(30d)"
    type_change: "full",
  tags: ["intermediate", "acceptance"]
);

SELECT
  customer_id,
  MAX(ordered_at) AS last_ordered_at,
  MAX(order_status) AS latest_order_status,
  COUNT(*) AS total_orders,
  SUM(line_total_cents) AS total_revenue_cents
FROM __ref("fact_orders")
GROUP BY customer_id
