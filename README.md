<p align="center">
  <img src="https://raw.githubusercontent.com/chio-labs/sqlbuild/main/.github/sqlbuild-logo-clean.png" alt="SQLBuild" width="100%">
</p>

<p align="center">
  Stop rebuilding what production already built. Change-aware SQL pipelines with all state in the warehouse.
</p>

SQLBuild is a SQL-first framework for building reliable warehouse pipelines. It points at your existing dbt project and makes your builds change-aware: it fingerprints your models, skips the ones that have not changed, and can reuse already-built tables from production instead of rebuilding them in dev. No SQLBuild models, no migration, no edits to your dbt files.

It is also a full standalone framework. All state is persisted as append-only tables in the warehouse alongside your data: no external state database, no manifest files, no paid add-on. It keeps a low, dbt-like floor for SQL models and adds ingestion, Python nodes, testing, and opt-in virtual environments as your project grows.

## Key features

- **Works with your existing dbt project.** Point SQLBuild at a dbt project and get change-aware builds and production reuse with zero SQLBuild models. It reads the manifest and drives the `dbt` CLI as a subprocess; it never edits your dbt files. See [dbt compatibility](https://docs.sqlbuild.com/concepts/dbt-compatibility/overview).
- **Reuse from production.** Clone or copy already-built relations from another target, or from a production-shaped git branch, instead of rebuilding them. Zero compute for models that match.
- **Change-aware builds by default.** Models, seeds, functions, and Python nodes are fingerprinted, source freshness is tracked, and unchanged work (including audits that already passed) is skipped. Pass `--force` to run everything selected.
- **Warehouse-native state.** All change-tracking state lives in append-only tables (`_sqlbuild_fingerprints`, `_sqlbuild_source_freshness`, `_sqlbuild_node_results`) in your warehouse schemas. No external state machine, no corruption risk.
- **Audits that block bad data.** Audits run before data reaches the target table. Full table builds materialize into a staging table and only promote if audits pass; incremental models validate each batch before DML.
- **SQL-first models, compile-time validation.** Define models as SQL files with `MODEL()` headers. SQLBuild resolves references, validates SQL, infers columns, checks contracts, and computes column lineage before anything runs, all offline.
- **Cursor-based incremental processing.** Automatic gap detection and resume, with microbatch mode for large ranges. No external checkpoint to maintain.
- **Ingestion and Python nodes.** Load external data with Python `@loader` functions, and run `@task`, `@asset`, and `@check` nodes as first-class members of the same DAG as your SQL models.
- **Testing.** Chained SQL unit tests that resolve intermediate models automatically, plus end-to-end scenarios with local DuckDB replay for fast CI with no warehouse.
- **Python you can read, Rust where it counts.** The framework is Python. For SQL parsing, validation, column inference, lineage, and transpilation, SQLBuild uses [Polyglot](https://github.com/tobilg/polyglot), a Rust reimplementation of SQLGlot's SQL analysis capabilities (MIT).

See the [documentation](https://docs.sqlbuild.com) for the full feature set, including providers, lifecycle hooks, Python macros, UDFs, custom materializations, data diffs, zero-copy cloning, and virtual environments.

## Works with your existing dbt project

Point SQLBuild at a dbt project and run a `sqb dbt` command. The first time, it bootstraps a minimal twin project from your `dbt_project.yml` and profile (reusing your dbt connection), then builds your selection with state recorded:

```bash
sqb dbt build --select path:models/marts
```

Run it again and the models that have not changed are skipped:

```
dbt (3 selected resources)
  planned models: 0 run, 3 current, 0 blocked
  skipped: all planned dbt models are current
```

Change one model and only that model, plus whatever depends on it, rebuilds. SQLBuild fingerprints your dbt models in the warehouse and prunes everything that is already current, so a second build skips the whole run. Your `--select` scope is always respected, and where it matters SQLBuild warns you about stale upstreams or downstreams left outside the selection. See [dbt compatibility](https://docs.sqlbuild.com/concepts/dbt-compatibility/overview).

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
```

## Example

A model is a SQL file with a `MODEL()` header and a `SELECT`. References use `__ref()` and `__source()`, and configuration, schema, and audits are declared inline:

```sql
MODEL (
  materialized table,
  columns (
    order_id (audits [not_null, unique]),
  ),
  tags [marts],
);

SELECT
  o.order_id,
  o.customer_id,
  p.amount_cents AS total_cents
FROM __ref("stg_orders") o
JOIN __ref("stg_payments") p USING (order_id)
```

A unit test mocks sources and asserts on the model, resolving every intermediate model automatically:

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
  SELECT 1 AS order_id, 100 AS customer_id, 1500 AS total_cents
)
SELECT 1
```

See the [documentation](https://docs.sqlbuild.com) for incremental models, scenarios, loaders, and more.

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

ClickHouse, Redshift, Trino, Spark, and Athena are on the way.

## Documentation

Full documentation is available at [docs.sqlbuild.com](https://docs.sqlbuild.com).

## Contributing

We welcome contributions. Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

SQLBuild is licensed under the [Apache License 2.0](LICENSE).
