<p align="center">
  <img src="https://raw.githubusercontent.com/chio-labs/sqlbuild/main/.github/sqlbuild-logo-clean.png" alt="SQLBuild" width="100%">
</p>

<p align="center">
  Verify early. Test properly. Deploy reversibly. SQL pipelines with the rigor of real software.
</p>

**Valid isn't the same as correct.** Your SQL compiles, runs, and returns rows; none of that means the number is right, and a silently-wrong number a stakeholder already trusted is the bug that actually hurts.

SQLBuild brings software-engineering rigor to SQL pipelines: catch errors before the warehouse runs them, test your logic locally, and opt into change-aware execution when you need it. It works as a standalone framework or points at your existing dbt project with no migration and no edits to your dbt files.

All state is persisted as append-only tables in the warehouse alongside your data: no external state database, no manifest files, no paid add-on. It keeps a low, dbt-like floor for SQL models and adds ingestion, Python nodes, and opt-in virtual environments as your project grows.

## Key features

- **Test your logic, not just your columns.** Chained SQL unit tests resolve every intermediate model from its real SQL, plus end-to-end scenarios with local DuckDB replay for fast CI with no warehouse. Catch wrong logic before it ships, not just nulls.
- **Verify early.** Define models as SQL files with `MODEL()` headers. SQLBuild resolves references, validates SQL, infers columns, checks contracts, and computes column lineage before anything runs, all offline. It fails at compile, not halfway through a warehouse run.
- **Fast and open static analysis.** SQL parsing, validation, column inference, lineage, and transpilation run on [Polyglot](https://github.com/tobilg/polyglot), a Rust SQL engine (MIT, 32+ dialects), so compile stays fast on large projects. The analysis is part of the Apache-2.0 core: no proprietary engine, no login, no paid tier.
- **Audits that block bad data.** Audits run before data reaches the target table. Full table builds materialize into a staging table and only promote if audits pass; incremental models validate each batch before DML.
- **Deploy reversibly (opt-in).** Virtual environments add instant low-copy branching, partial promotion, rollback, checkpoints, and reconciliation. Opt-in, not a tax you pay upfront.
- **Opt-in change-aware execution.** Models, seeds, UDFs, and Python nodes are fingerprinted, and source freshness is tracked. Commands run the selected work by default; pass `--changes-only` or set `changes_only = true` to skip work that is already current.
- **Works with your existing dbt project.** Point SQLBuild at a dbt project and run ordinary dbt selections alongside SQLBuild models. It reads the manifest and drives the `dbt` CLI as a subprocess; it never edits your dbt files. dbt-native `--state` and `--defer` remain available, while `sqb dbt clone` and `sqb dbt diff` work against a production-shaped git ref. See [dbt compatibility](https://docs.sqlbuild.com/concepts/dbt-compatibility/overview).
- **Warehouse-native state.** All change-tracking state lives in append-only tables (`_sqlbuild_fingerprints`, `_sqlbuild_source_freshness`, `_sqlbuild_node_results`) in your warehouse schemas. No external state machine, no corruption risk.
- **Cursor-based incremental processing.** Automatic gap detection and resume, with microbatch mode for large ranges. No external checkpoint to maintain.
- **Ingestion and Python nodes.** Load external data with Python `@loader` functions, and run `@task`, `@asset`, and `@check` nodes as first-class members of the same DAG as your SQL models.

See the [documentation](https://docs.sqlbuild.com) for the full feature set, including providers, lifecycle hooks, Python macros, UDFs, custom materializations, data diffs, zero-copy cloning, and virtual environments.

Enable change-aware execution for individual commands with `--changes-only`, for a project with `[settings]`, or for one target:

```toml
[settings]
changes_only = true

[targets.dev]
changes_only = true
```

The CLI flag takes precedence, followed by the selected target, explicit local settings, and project settings. For native `plan` and `build` execution, the full selected scope runs when no configuration source enables changes-only mode; the former execution `--force` option is no longer used.

## Works with your existing dbt project

Point SQLBuild at a dbt project and run a `sqb dbt` command. The first time, it bootstraps a minimal twin project from your `dbt_project.yml` and profile (reusing your dbt connection), then runs your selection through dbt:

```bash
sqb dbt build --select path:models/marts
```

SQLBuild preserves dbt-native state and defer arguments when you need dbt's own state-aware selection:

```bash
sqb dbt build --state path/to/state --defer --select state:modified+
```

Ordinary `sqb dbt plan`, `run`, `build`, and `test` commands do not fingerprint dbt models, inspect production state, or clone deferred relations automatically. Use `sqb dbt clone` and `sqb dbt diff` explicitly for production-shaped comparisons. See [dbt compatibility](https://docs.sqlbuild.com/concepts/dbt-compatibility/overview).

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
  SELECT
    1 AS payment_id,
    1 AS order_id,
    1500 AS amount_cents,
    'credit_card' AS method
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
