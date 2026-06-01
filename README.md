<p align="center">
  <img src="https://raw.githubusercontent.com/chio-labs/sqlbuild/main/.github/sqlbuild-logo-clean.png" alt="SQLBuild" width="100%">
</p>

<p align="center">
  Typed, test-first SQL pipelines with local E2E testing.
</p>

SQLBuild is a SQL pipeline framework that validates SQL at compile time, blocks bad data before promotion, and runs full E2E tests with no warehouse required.

## Key features

- **SQL unit tests that chain across models** - Mock your sources, assert on the model you care about, and SQLBuild resolves every intermediate model automatically. One test file can be a full integration test across your pipeline.
- **End-to-end scenarios with local replay** - Define coherent fixture worlds, run the real project graph in an isolated warehouse slice, capture JSONL snapshots, and replay them locally through DuckDB for fast CI feedback.
- **Audits that block bad data** - Audits run before data reaches the target table. For full table builds, SQLBuild materializes into a staging table and only promotes if audits pass. For incremental models, delta-phase audits validate each batch before DML.
- **Python macros, not Jinja** - Macros are real Python functions. Testable, debuggable, and composable with standard tooling.
- **Change-aware incremental rebuilds** - Fingerprint-based query change detection, schema diff tracking, and configurable backfill policies with automatic cascade through the DAG.
- **Cursor-based incremental processing** - Automatic gap detection and resume. If a model fails for several runs, the next build replays from where it left off. Microbatch mode splits large ranges into configurable batches.
- **User-defined functions** - SQL and Python UDFs managed as project resources, with table functions for predicate-pushdown-friendly alternatives to final-layer views.
- **Environment diffs** - Compare schemas and row-level data between environments with `sqb diff prod:dev`.
- **Zero-copy cloning** - Branch environments instantly with `sqb clone` without duplicating data. No `manifest.json` required.
- **Source loaders** - Load external data into source tables with Python functions. Supports incremental write strategies (table, append, delete\_insert, merge), cursor-based loading, loader-to-loader dependencies, and concurrent execution. Loaders run automatically during builds.
- **Custom materializations** - Write materialization logic in Python with full framework integration, including audit hooks, schema change signals, and query change detection.
- **Path-between selectors** - `--select fact_orders~daily_activity_rollup` selects every model on the shortest path between two nodes.
- **Advanced virtual environments** - Optional state-backed workflows for low-copy branching, promotion, and rollback when your team is ready to operate a shared state store.

## Quick start

```bash
pip install sqlbuild
# or
uv pip install sqlbuild
```

Create and run the playground project:

```bash
sqb playground waffle-shop
cd waffle-shop
sqb plan
sqb build
sqb test
sqb scenario test
```


## How it works

1. **Define** your models as SQL files with `MODEL()` headers that declare configuration, schema, and audits inline
2. **Compile** to resolve references, validate SQL, infer column types, check contracts, and compute column lineage - all offline
3. **Plan** what needs to change based on fingerprints, schema diffs, and backfill policies
4. **Build** by executing the plan: materializing models, validating data before promotion, and ensuring bad data never reaches production
5. **Test** with chained unit tests, E2E scenario tests, and local replay through DuckDB - no warehouse required

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
FROM __source("raw__orders")
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
  post_hook ["grant select on @@CTX:target.qualified to role analytics"],
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
__source__raw__orders AS (
  @mock_orders()
),
__source__raw__payments AS (
  SELECT 1 AS payment_id, 1 AS order_id, 1500 AS amount_cents, 'credit_card' AS method
),
__expected__fact_orders AS (
  SELECT 1 AS order_id, 100 AS customer_id, 1500 AS total_cents,
         'credit_card' AS payment_method
),
__assert__no_negative_totals AS (
  SELECT * FROM __ref("fact_orders") WHERE total_cents < 0
)
SELECT 1
```

An end-to-end scenario:

```sql
SCENARIO (
  description "Customer refund updates daily revenue correctly",
  tags [revenue, refund],
);

WITH
__source__raw__orders AS (
  SELECT 1 AS order_id, DATE '2026-01-01' AS order_date, 100.00 AS amount
),
__source__raw__refunds AS (
  SELECT 1 AS refund_id, 1 AS order_id, DATE '2026-01-01' AS refund_date, 25.00 AS amount
),
__expected__daily_revenue AS (
  SELECT DATE '2026-01-01' AS order_date, 75.00 AS revenue
),
__assert__all_refunds_linked AS (
  SELECT * FROM __ref("fact_refunds") WHERE order_id IS NULL
)
SELECT 1
```

Scenario files live under `tests/scenarios/**/*.sql`. Run them in the target warehouse with:

```bash
sqb scenario test
sqb scenario test --select revenue__customer_refund --retain
sqb scenario test --select tests/scenarios/revenue --exclude revenue__slow_refund
```

Capture local replay snapshots as JSONL under `tests/_scenario_snapshots/<scenario_name>/`:

```bash
sqb scenario capture --select revenue__customer_refund
sqb scenario capture --select-file changed_scenarios.txt --exclude revenue__slow_refund
sqb scenario test --select revenue__customer_refund --local
sqb scenario test --local --sync-snapshots
sqb scenario test --local --refresh
```

Snapshots are committable test data. Review them for sensitive values before committing.

A source loader:

```python
from sqlbuild.loaders import loader
from sqlbuild.executor.load.models import LoaderContext

@loader
def raw_orders(ctx: LoaderContext) -> list[dict[str, object]]:
    if ctx.current_cursor_value is None:
        return fetch_all_orders()
    return fetch_orders_since(ctx.current_cursor_value)
```

Python loaders should return rows for SQLBuild to write, such as a list of dictionaries
or another supported tabular row object. Self-managed loaders that write their own data
can return `None`.

Bound to a source in `sources/*.yml`:

```yaml
sources:
  - name: raw_orders
    managed: true
    write_strategy: delete_insert
    cursor_column: ordered_at
    columns:
      - name: id
        type: INTEGER
      - name: ordered_at
        type: TIMESTAMP
```

## Documentation

Full documentation is available at [docs.sqlbuild.com](https://docs.sqlbuild.com).

## Contributing

We welcome contributions. Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

SQLBuild is licensed under the [Apache License 2.0](LICENSE).
