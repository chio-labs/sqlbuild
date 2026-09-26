<p align="center">
  <img src="https://raw.githubusercontent.com/chio-labs/sqlbuild/main/.github/sqlbuild-logo-clean.png" alt="SQLBuild" width="100%">
</p>

<p align="center">
  <strong>The refactorable warehouse.</strong> Verify early, test properly, and refactor safely.
</p>

<p align="center">
  <a href="https://sqlbuild.com">Website</a> ·
  <a href="https://sqlbuild.com/docs/">Docs</a> ·
  <a href="https://sqlbuild.com/docs/quickstart/">Quickstart</a> ·
  <a href="https://sqlbuild.com/docs/roadmap/">Roadmap</a>
</p>

Change your warehouse as often as your code. SQLBuild brings compile-time checks, tests and diffs to
your SQL, so change is safe. It is a free, open-source framework for SQL and Python data pipelines,
and it keeps its state in append-only tables in your own warehouse: no external state database, no
manifest files and no paid tier.

## Quick start

```bash
pip install sqlbuild
sqb playground waffle-shop
cd waffle-shop
sqb plan
sqb build
sqb test
```

The playground runs on local DuckDB, with no warehouse credentials.

## What it does

### Catch mistakes before anything runs

- **Compile-time checks.** SQLBuild resolves references, validates SQL, infers column types, checks
  [contracts](https://sqlbuild.com/docs/concepts/models/contracts/) and computes column lineage,
  all offline. A typo'd column fails in seconds, not halfway through a warehouse run.
- **Your conventions as rules.** Built-in and custom Python
  [rules](https://sqlbuild.com/docs/concepts/rules/) turn review comments into compile errors: for
  example, marts can't read sources directly, or every final model declares its key.

### Prove it works

- **Tests across models.** SQL [tests](https://sqlbuild.com/docs/concepts/testing/) mock the
  sources and check the result through every model in between, with macros as test helpers. Macro,
  UDF and table-function tests are built in.
- **End-to-end scenarios.** Build the real graph against fixture data, capture fixtures from the
  warehouse, and replay them locally on DuckDB in CI.
  See [scenarios](https://sqlbuild.com/docs/concepts/scenarios/).
- **Audits and diffs.** Audits run before data reaches the target table, and
  [data diffs](https://sqlbuild.com/docs/concepts/diff/) compare dev against prod or any query.

### Change it without rebuilding everything

- **Renames keep their history.** Rename or move an incremental or snapshot model and SQLBuild
  [migrates](https://sqlbuild.com/docs/concepts/models/migrations/) the existing table instead of
  rebuilding it.
- **Replay on change.** When a model's SQL changes, choose how far back to reprocess, from only the
  new data to the last 14 days to a full rebuild, with
  [`replay_on_change`](https://sqlbuild.com/docs/concepts/incremental/#replay-on-change).
- **Macros don't have to be global.** Keep macros, enums and constants next to the models that use
  them, and preview what a move would break with `sqb scope`. See
  [declaration scopes](https://sqlbuild.com/docs/concepts/declaration-scopes/).
- **Tidy up safely.** The [janitor](https://sqlbuild.com/docs/cli/janitor/) archives stale tables
  before anything is deleted.

Ingestion with Python loaders, and Python tasks, assets and checks, run in the same graph as your SQL
models. See the [docs](https://sqlbuild.com/docs/) for everything else.

## Example

A model is a SQL file with a `MODEL()` header and a `SELECT`:

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

A test mocks the sources and asserts on the model, resolving every model in between from its real
SQL:

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

## Warehouses

| Warehouse | Status |
|-----------|--------|
| Snowflake | Supported |
| DuckDB | Supported |
| MotherDuck | Supported |
| PostgreSQL | Supported |
| BigQuery | Beta |
| Databricks | Beta |
| SQL Server | Beta |

Snowflake is the main target. Beta adapters build, test and plan, but have had less production use
so far. See [adapters](https://sqlbuild.com/docs/concepts/adapters/).

## Free and independent

SQLBuild is Apache 2.0 and will stay free: no paid tier, no commercial edition, and no feature held
back for one. Its state lives in your warehouse, next to your data. See the
[roadmap](https://sqlbuild.com/docs/roadmap/) for what's next.

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

SQLBuild is licensed under the [Apache License 2.0](LICENSE).
