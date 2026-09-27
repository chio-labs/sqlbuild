# SQLBuild Loader-Focused Waffle Shop Playground

This playground is a local DuckDB project focused on chained source loaders.

## Try It

```bash
sqb plan --select +customer_revenue
sqb build --select +customer_revenue
sqb build --select +customer_revenue
sqb query "SELECT * FROM customer_revenue ORDER BY customer_id"
sqb load --select raw_orders
```

Repeated `sqb build` runs cause source-loader data to grow or change:

- order events append new rows
- customer state merges updates and new entities
- prices refresh in place

## What This Shows

The complete source contracts also support offline `sqb compile` column and type checks.
DuckDB rejects proven bind-time type errors; accepted conversions with data-dependent risks are
non-blocking W21x warnings. PostgreSQL, Snowflake, and BigQuery use their own coercion rules;
MotherDuck uses DuckDB's rules. Unknown types remain unchecked. The escape hatches are
`MODEL (sql_analysis false)`, the corresponding path default, and `--no-sql-analysis`.

- chained intermediate source loaders
- different intermediate write strategies
- terminal managed source loaders
- downstream models reading loaded sources
- repeated builds that visibly evolve data
