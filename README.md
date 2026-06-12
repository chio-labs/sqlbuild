<p align="center">
  <img src="https://raw.githubusercontent.com/chio-labs/sqlbuild/main/.github/sqlbuild-logo-clean.png" alt="SQLBuild" width="100%">
</p>

<p align="center">
  Change-aware SQL pipelines: only rebuild what changed, with all state in the warehouse.
</p>

SQLBuild is a SQL-first framework for building reliable warehouse pipelines. Every build is change-aware by default -- models, seeds, functions, and Python nodes are fingerprinted, source freshness is tracked, and unchanged work (including audits that already passed) is skipped automatically. All state is persisted as append-only tables in the warehouse alongside your data. No external state database, no manifest files, no paid add-on.

It keeps a low, dbt-like floor for SQL models and can run alongside an existing dbt project. It adds ingestion, Python nodes, providers, and opt-in virtual environments for more advanced use cases, letting you expand scope as your project naturally grows.

## Key features

- **Change-aware builds by default** -- Fingerprint-based tracking for models, seeds, functions, and Python nodes. Source freshness observation. Audits skipped when the model version hasn't changed. Cascade propagation with configurable replay windows (`replay_on_change`). Pass `--force` to override and run everything selected.
- **Warehouse-native state** -- All change-tracking state lives in append-only tables (`_sqlbuild_fingerprints`, `_sqlbuild_source_freshness`) in your warehouse schemas. No external state database, no state machine, no corruption risk. The planner reads the latest row per identity, compares, and appends after successful builds.
- **Reuse from production** -- Dev targets can opt into `reuse_from` to clone or copy unchanged relations from another target (e.g. prod) instead of rebuilding. Zero compute for models that match.
- **Audits that block bad data** -- Audits run before data reaches the target table. For full table builds, SQLBuild materializes into a staging table and only promotes if audits pass. For incremental models, delta-phase audits validate each batch before DML.
- **SQL-first models with compile-time validation** -- Define models as SQL files with `MODEL()` headers while SQLBuild resolves references, validates SQL, infers columns, checks contracts, and computes lineage before anything runs.
- **Cursor-based incremental processing** -- Automatic gap detection and resume. If a model fails for several runs, the next build replays from where it left off. Microbatch mode splits large ranges into configurable batches.
- **Source freshness** -- Track whether external source data has changed via adapter metadata, column queries, or custom SQL. Lag tolerance prevents jitter from triggering unnecessary rebuilds. `sqb freshness` observes freshness without running a build; `--fail-on-stale` gates CI pipelines.
- **Source loaders** -- Load external data into source tables with Python `@loader` functions. Supports incremental write strategies (table, append, delete\_insert, merge), cursor-based loading, and concurrent execution. Loaders run automatically during builds.
- **Python nodes** -- Tasks (`@task`), assets (`@asset`), checks (`@check`), and factories (`@factory`) as first-class DAG nodes alongside SQL models. Identity-tracked with source and dependency diffs shown in the plan.
- **Providers** -- Shared runtime services (API clients, connections, config) injected into Python nodes and hooks by parameter name. Backed by pydantic-settings for validation and environment variable support.
- **Python lifecycle hooks** -- Typed `sql("...")`/`python("hook_name")` hooks with compile-time validation and a `HookContext` API. Provider injection supported.
- **Python macros, not Jinja** -- Macros are real Python functions. Testable, debuggable, and composable with standard tooling.
- **User-defined functions** -- SQL and Python UDFs managed as project resources, with table functions for predicate-pushdown-friendly alternatives to final-layer views.
- **Custom materializations** -- Write materialization logic in Python with full framework integration, including audit hooks, schema change signals, and query change detection.
- **SQL unit tests that chain across models** -- Mock your sources, assert on the model you care about, and SQLBuild resolves every intermediate model automatically. One test file can be a full integration test across your pipeline.
- **End-to-end scenarios with local replay** -- Define coherent fixture worlds, run the real project graph in an isolated warehouse slice, capture JSONL snapshots, and replay them locally through DuckDB for fast CI feedback.
- **Data diffs** -- Compare schemas and row-level data between targets with `sqb diff prod:dev`.
- **Zero-copy cloning** -- Branch targets instantly with `sqb clone` without duplicating data. No `manifest.json` required.
- **Path-between selectors** -- `--select fact_orders~daily_activity_rollup` selects every model on the shortest path between two nodes.
- **Virtual environments (alpha)** -- Opt-in state-backed workflows for versioned model outputs, zero-copy branching, instant promotion and rollback, per-PR preview environments. Seeds are versioned alongside models. State stored in PostgreSQL or DuckDB, scoped per environment.
- **Python you can read, Rust where it counts** -- The framework is Python. For SQL parsing, validation, column inference, lineage, and transpilation, SQLBuild uses [Polyglot](https://github.com/tobilg/polyglot), a Rust reimplementation of SQLGlot's SQL analysis capabilities (MIT, 32+ dialects).
- **Dagster and Rivers integrations** -- Models, loaders, tasks, assets, and checks map to Dagster/Rivers assets with dependency edges preserved. Python checks become asset checks.

## Quick start

```bash
pip install sqlbuild
# or
uv pip install sqlbuild
```

Create and run the included playground project:

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
2. **Compile** to resolve references, validate SQL, infer column types, check contracts, and compute column lineage -- all offline
3. **Plan** what needs to change by comparing fingerprints, source freshness, seed content, and Python node identities against the warehouse state. Unchanged models, seeds, audits, and Python nodes are skipped. Production relations can optionally be reused when version identities match.
4. **Build** by executing the plan: materializing only what changed, validating data before promotion, and ensuring bad data never reaches production
5. **Test** with chained unit tests, E2E scenario tests, and local replay through DuckDB -- no warehouse required

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
  replay_on_change full,
  tags [marts],
  post_hooks [sql('GRANT SELECT ON @@CTX:destination.qualified TO analyst_role')],
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

## Supported adapters

| Adapter | Status |
|---------|--------|
| DuckDB | Supported |
| MotherDuck | Supported |
| Snowflake | Supported |
| BigQuery | Supported |
| Databricks | Supported |
| PostgreSQL | Supported |
| SQL Server | Supported |

## Documentation

Full documentation is available at [docs.sqlbuild.com](https://docs.sqlbuild.com).

## Contributing

We welcome contributions. Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

SQLBuild is licensed under the [Apache License 2.0](LICENSE).
