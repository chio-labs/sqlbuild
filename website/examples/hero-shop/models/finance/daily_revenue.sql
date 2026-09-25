MODEL (
  materialized incremental,
  incremental_strategy delete_insert,
  cursor revenue_date,
  cursor_type timestamp,
  cursor_grain day,
);

SELECT CAST('2026-04-01' AS DATE) AS revenue_date, 2850 AS total_revenue_cents
