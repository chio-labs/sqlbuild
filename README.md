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

- **Test your logic, not just your columns.** Multi-model SQL tests resolve every intermediate model from its real SQL, plus end-to-end scenarios with local DuckDB replay for fast CI with no warehouse. Catch wrong logic before it ships, not just nulls.
- **Verify early.** Define models as SQL files with `MODEL()` headers. SQLBuild resolves references, validates SQL, infers columns, checks contracts, and computes column lineage before anything runs, all offline. It fails at compile, not halfway through a warehouse run.
- **Fast and open static analysis.** SQL parsing, validation, column inference, lineage, and transpilation run on [Polyglot](https://github.com/tobilg/polyglot), a Rust SQL engine (MIT, 32+ dialects), so compile stays fast on large projects. The analysis is part of the Apache-2.0 core: no proprietary engine, no login, no paid tier.
- **Audits that block bad data.** Audits run before data reaches the target table. Full table builds materialize into a staging table and only promote if audits pass; incremental models validate each batch before DML.
- **Deploy reversibly (opt-in).** Virtual environments add instant low-copy branching, partial promotion, rollback, checkpoints, and reconciliation. Opt-in, not a tax you pay upfront.
- **Opt-in change-aware execution.** Models, seeds, UDFs, and Python nodes are fingerprinted, and source freshness is tracked. In virtual environments, pass `--changes-only` or set `changes_only = true` to skip work that is already current; commands otherwise run the full selected scope.
- **Works with your existing dbt project.** Point SQLBuild at a dbt project and run ordinary dbt selections alongside SQLBuild models. It reads the manifest and drives the `dbt` CLI as a subprocess; it never edits your dbt files. dbt-native `--state` and `--defer` remain available for production-shaped, state-aware selections. See [dbt compatibility](https://docs.sqlbuild.com/concepts/dbt-compatibility/overview).
- **Warehouse-native state.** All change-tracking state lives in append-only tables (`_sqlbuild_fingerprints`, `_sqlbuild_source_freshness`, `_sqlbuild_node_results`) in your warehouse schemas. No external state machine, no corruption risk.
- **Cursor-based incremental processing.** Automatic gap detection and resume, with microbatch mode for large ranges. No external checkpoint to maintain.
- **Ingestion and Python nodes.** Load external data with Python `@loader` functions, and run `@task`, `@asset`, and `@check` nodes as first-class members of the same DAG as your SQL models.

See the [documentation](https://docs.sqlbuild.com) for the full feature set, including providers, lifecycle hooks, Python macros, UDFs, custom materializations, data diffs, zero-copy cloning, and virtual environments.

## Works with your existing dbt project

Point SQLBuild at a dbt project and run a `sqb dbt` command. The first time, it bootstraps a minimal twin project from your `dbt_project.yml` and profile (reusing your dbt connection), then runs your selection through dbt:

```bash
sqb dbt build --select path:models/marts
```

SQLBuild preserves dbt-native state and defer arguments when you need dbt's own state-aware selection:

```bash
sqb dbt build --state path/to/state --defer --select state:modified+
```

Ordinary `sqb dbt plan`, `run`, and `build` commands do not fingerprint dbt models or inspect production state automatically. Use dbt-native `--state`/`--defer` for production-shaped comparisons. See [dbt compatibility](https://docs.sqlbuild.com/concepts/dbt-compatibility/overview).

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

## Concurrent microbatches

Native `delete_insert` microbatch models can opt into parallel batch execution. Serial execution is
the default and remains recommended unless parallel batches provide a meaningful runtime benefit.
Enable the project capability and set a per-model ceiling:

```toml
[settings]
microbatch_concurrency = true
microbatch_unaccounted_partition_policy = "synthesize"
```

```sql
MODEL (
  materialized incremental,
  incremental_mode microbatch,
  incremental_strategy delete_insert,
  cursor event_time,
  cursor_type timestamp,
  cursor_grain hour,
  batch_size 1h,
  batch_concurrency 4,
);
```

`batch_concurrency` is a model ceiling, not a separate worker pool. Batches share the build's global
`concurrency` limit and connection pool with every other DAG node. First-run and full-refresh target
bootstrap remain serialized. Concurrent batches are rejected for adapters that have not explicitly
declared same-target concurrent delete/insert support.

Every native microbatch, including serial models and projects where the capability is disabled,
records successful half-open partitions and their model fingerprints. Standard builds use the
warehouse `_sqlbuild_microbatches` table. Virtual builds store equivalent events in the configured
DuckDB or Postgres state backend and scope them to the immutable physical model version. Virtual
builds renew a physical-version lease while mutating shared data; standard-mode orchestrators must
prevent overlapping invocations for the same model destination.

The append-only history distinguishes physical continuity from fingerprint continuity. Known gaps
are recovered before new normal work. Automatic `replay_on_change` ranges are durable and
version-specific, while explicit backfills remain one-shot requests. If destination progress is not
explained by retained history, `microbatch_unaccounted_partition_policy` controls reconciliation:

- `synthesize` accepts inferred physical coverage and records an unknown fingerprint.
- `recover_empty` counts candidates in bounded chunks, reruns empty intervals, and synthesizes
  non-empty intervals.
- `recover_all` reruns every unaccounted interval without a preliminary count.

Synthetic coverage preserves forward progress but weakens version guarantees and remains visible in
warnings and JSON output. Target DML and event insertion do not require a cross-system transaction;
idempotent `delete_insert` recovery handles failures between those operations.

## Kata SQL architecture checks

Kata is SQLBuild's opt-in, error-only SQL model shape checker. It runs offline over the compiled
project, reports coded faults with remediations, and never rewrites SQL. Its built-in lifecycle is
native: Rust resolves rule policy, parses each model, evaluates built-ins, applies suppressions,
and owns the persistent cache and deterministic result ordering.

Kata is disabled until the project selects at least one rule. Select the complete built-in policy
in `sqlbuild_project.toml` with its namespace prefix:

```toml
[kata]
select = ["SQBK"]
```

`SQBK` activates every built-in rule. Narrower prefixes such as `SQBKS` activate one family, exact
codes select individual rules, and `ignore` removes matching rules. Audit, unit-test, and custom-rule
test-case minimums each default to one and can be overridden under `[kata.thresholds]`.

Run `sqb kata`, inspect metadata with `sqb kata rule SQBKS101`, and generate agent guidance from
the same active ruleset with `sqb kata skills`. Use `sqb kata skills --check` in CI to detect stale
guidance. `--json`, `--select`, and `--exclude` are available for automation and model scoping.

Repository rules use the public API:

```python
from sqlbuild.kata import RuleContext, kata


@kata(
    code="XSQBKP001",
    family="prices",
    slug="typed-currency",
    message="price models must declare a currency column",
    remediation="Declare currency in the MODEL columns contract at this model path.",
)
def typed_currency(*, model, ctx: RuleContext):
    return [] if any(column.name == "currency" for column in ctx.declared_columns) else [
        ctx.path_fault()
    ]
```

Load repository-owned files through `rule_paths = ["kata/rules"]` or dotted packages through
`rule_modules`. Test each custom rule with `RuleCase` and `evaluate_rule`. Selecting custom rules
disables caching unless `[kata.cache] require_cacheable = true`; cacheable rules may import only
the supported pure modules and must access project files through `RuleContext`.

Python is used only for the SQLBuild compiler adapter and selected custom rules. Built-in-only
runs cross into the native engine once as a compiled model batch and do not materialize or walk
Python AST objects. A selected custom rule can still use the public `RuleContext` and raw
Polyglot AST escape hatch; its findings rejoin native suppression, ordering, and cache policy.

Exact `rule_exceptions` require a rule, file, and reason and fail when stale. Broader
`rule_ignores` and lone-star allowances also require reasons but are intentionally not
stale-checked.

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

## Snowflake cost estimates

Native Snowflake builds automatically show a compact per-run busy-compute estimate. SQLBuild
attributes visible overlapping query intervals fairly across active queries, converts attributed
seconds using the warehouse-size credit rate, and estimates USD from the configured rate:

```toml
[cost]
usd_per_credit = 3.00
```

The default is `3.00` USD per credit and is visibly marked as a default. Configure the value with
your Snowflake contract rate. Use `sqb cost`, `sqb cost latest`, `sqb cost <run_id>`, or
`sqb cost history --since 7d` to inspect persisted records. `--json` and `--json-output PATH`
provide a versioned, decimal-safe output contract. Pending detail records are refreshed from
Snowflake when inspected again.

These values are attributed compute credits and estimated cost, not Snowflake-billed credits or
invoice reconciliation. The estimate uses only query history visible to the executing role and
does not reconstruct invisible concurrent work, warehouse resume or idle tail, the 60-second
minimum, cloud-services credits, contract adjustments, or multi-cluster billing. Run metadata and
query IDs are stored under `target/runs/<run_id>/`; raw SQL is not persisted.

## Documentation

Full documentation is available at [docs.sqlbuild.com](https://docs.sqlbuild.com).

## Contributing

We welcome contributions. Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

SQLBuild is licensed under the [Apache License 2.0](LICENSE).
