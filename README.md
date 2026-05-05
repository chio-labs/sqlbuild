<p align="center">
  <img src="https://raw.githubusercontent.com/chio-labs/sqlbuild/main/.github/sqlbuild-logo-rounded.png" alt="SQLBuild" width="560">
</p>

<p align="center">
  Typed, test-first SQL pipelines with change-aware incremental rebuilds.
</p>

SQLBuild is a framework for building batch SQL transformation pipelines where correctness and extensibility are first-class concerns.

## Key features

- **SQL unit tests that chain across models** - Mock your sources, assert on the model you care about, and SQLBuild resolves every intermediate model automatically. One test file can be a full integration test across your pipeline.
- **Audits that block bad data** - Audits run before data reaches the target table. For full table builds, SQLBuild materializes into a staging table and only promotes if audits pass. For incremental models, delta-phase audits validate each batch before DML.
- **Python macros, not Jinja** - Macros are real Python functions. Testable, debuggable, and composable with standard tooling.
- **Change-aware incremental rebuilds** - Fingerprint-based query change detection, schema diff tracking, and configurable backfill policies with automatic cascade through the DAG.
- **Cursor-based incremental processing** - Automatic gap detection and resume. If a model fails for several runs, the next build replays from where it left off. Microbatch mode splits large ranges into configurable batches.
- **User-defined functions** - SQL and Python UDFs managed as project resources, with table functions for predicate-pushdown-friendly alternatives to final-layer views.
- **Environment diffs** - Compare schemas and row-level data between environments with `sqb diff prod:dev`.
- **Zero-copy cloning** - Branch environments instantly with `sqb clone` without duplicating data. No `manifest.json` required.
- **Custom materializations** - Write materialization logic in Python with full framework integration, including audit hooks, schema change signals, and query change detection.
- **Path-between selectors** - `--select fact_orders~daily_activity_rollup` selects every model on the shortest path between two nodes.

## Quick start

```bash
pip install sqlbuild
# or
uv add sqlbuild
```

Clone the repo and run the waffle shop example:

```bash
git clone https://github.com/chio-labs/sqlbuild.git
cd sqlbuild
uv sync
sqb --project-dir examples/waffle_shop plan
sqb --project-dir examples/waffle_shop build
```


## How it works

1. **Define** your models as SQL files with `MODEL()` headers that declare configuration, schema, and audits inline
2. **Compile** to resolve references, validate SQL (with SQLGlot), and expand Python macros
3. **Plan** what needs to change based on fingerprints, schema diffs, and backfill policies
4. **Build** by executing the plan: materializing models, validating data before promotion, and ensuring bad data never reaches production
5. **Iterate** with first-class support for chained unit tests, zero-copy cloning, and deferred builds - fast feedback without rebuilding the world

## Example

A simple staging model:

```sql
MODEL (
  materialized view,
  tags [staging],
);

SELECT
  id AS order_id,
  customer_id,
  ordered_at,
  status
FROM __source("raw_orders")
```

An incremental model with microbatch processing:

```sql
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
);

SELECT
  DATE_TRUNC('hour', o.ordered_at) AS activity_hour,
  COUNT(*) AS orders_placed,
  SUM(o.quantity) AS waffles_ordered
FROM __ref("fact_orders") o
GROUP BY DATE_TRUNC('hour', o.ordered_at)
```

A chained unit test:

```sql
TEST();

WITH
__source__raw_orders AS (
  @mock_orders()
),
__source__raw_payments AS (
  SELECT 1 AS payment_id, 1 AS order_id, 1500 AS amount_cents, 'credit_card' AS method
),
__expected__fact_orders AS (
  SELECT 1 AS order_id, 100 AS customer_id, 1500 AS total_cents,
         'credit_card' AS payment_method
)
SELECT 1
```

## Documentation

Full documentation is available at [docs.sqlbuild.com](https://docs.sqlbuild.com).

## Contributing

We welcome contributions. Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

SQLBuild is licensed under the [Apache License 2.0](LICENSE).
