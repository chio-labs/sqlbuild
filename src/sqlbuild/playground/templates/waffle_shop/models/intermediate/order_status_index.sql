MODEL (
  materialized incremental,
  incremental_strategy delete_insert,
  unique_key [order_id],
  cursor order_id,
  cursor_type integer,
  on_schema_change append_new_columns,
  schema_change_backfill (
    add_column bounded-7d,
    type_change full,
  ),
  tags [intermediate, acceptance],
  description "Integer-cursor incremental projection over fact orders.",
  columns (
    order_id (audits [not_null, unique]),
  ),
);

SELECT
  order_id,
  customer_id,
  order_status,
  ordered_at,
  line_total_cents
FROM __ref("fact_orders")
