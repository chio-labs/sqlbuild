<p align="center">
  <img src="https://raw.githubusercontent.com/chio-labs/sqlbuild/main/.github/sqlbuild-logo-clean.png" alt="SQLBuild" width="100%">
</p>

<p align="center">
  Verify early. Test properly. Deploy reversibly. SQL pipelines with the rigor of real software.
</p>

**Valid isn't the same as correct.** Your SQL compiles, runs, and returns rows; none of that means the number is right, and a silently-wrong number a stakeholder already trusted is the bug that actually hurts.

SQLBuild brings software-engineering rigor to SQL pipelines: catch errors before the warehouse runs them, test your logic locally, and opt into change-aware execution when you need it. It is a standalone, open-source framework for building SQL and Python data pipelines.

All state is persisted as append-only tables in the warehouse alongside your data: no external state database, no manifest files, no paid add-on. Start with straightforward SQL models, then add ingestion, Python nodes, and opt-in virtual environments as your project grows.

## Key features

- **Test your logic, not just your columns.** Multi-model SQL tests resolve every intermediate model from its real SQL, plus end-to-end scenarios with local DuckDB replay for fast CI with no warehouse. Catch wrong logic before it ships, not just nulls.
- **Verify early.** Define models as SQL files with `MODEL()` headers. SQLBuild resolves references, validates SQL, infers columns, checks contracts, and computes column lineage before anything runs, all offline. It fails at compile, not halfway through a warehouse run.
- **Fast and open static analysis.** SQL parsing, validation, column inference, lineage, and transpilation run on [Polyglot](https://github.com/tobilg/polyglot), a Rust SQL engine (MIT, 32+ dialects), so compile stays fast on large projects. The analysis is part of the Apache-2.0 core: no proprietary engine, no login, no paid tier.
- **Audits that block bad data.** Audits run before data reaches the target table. Full table builds materialize into a staging table and only promote if audits pass; incremental models validate each batch before DML.
- **Deploy reversibly (opt-in).** Virtual environments add instant low-copy branching, partial promotion, rollback, checkpoints, and reconciliation. Opt-in, not a tax you pay upfront.
- **Opt-in change-aware execution.** Models, seeds, UDFs, and Python nodes are fingerprinted, and source freshness is tracked. In virtual environments, pass `--changes-only` or set `changes_only = true` to skip work that is already current; commands otherwise run the full selected scope.
- **Warehouse-native state.** All change-tracking state lives in append-only tables (`_sqlbuild_fingerprints`, `_sqlbuild_source_freshness`, `_sqlbuild_node_results`) in your warehouse schemas. No external state machine, no corruption risk.
- **Cursor-based incremental processing.** Automatic gap detection and resume, with microbatch mode for large ranges. No external checkpoint to maintain.
- **Ingestion and Python nodes.** Load external data with Python `@loader` functions, and run `@task`, `@asset`, and `@check` nodes as first-class members of the same DAG as your SQL models.

See the [documentation](https://docs.sqlbuild.com) for the full feature set, including providers, lifecycle hooks, Python macros, UDFs, custom materializations, data diffs, zero-copy cloning, and virtual environments. To coordinate dbt and SQLBuild projects, see the [dbt compatibility guide](https://docs.sqlbuild.com/concepts/dbt-compatibility/overview).

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

Relation fixtures can omit a column when the compiled test or scenario closure requires it and
SQLBuild knows its adapter type, unless the column is explicitly non-nullable. SQLBuild completes
that test-only fixture column with a typed null such as `CAST(NULL AS VARCHAR)`; it never changes
model SQL or warehouse defaults. Required columns declared with `nullable false` and columns with
unknown types must be supplied explicitly. When the relation's complete column set is authoritative,
misspelled or unknown supplied fixture columns are rejected.

See the [documentation](https://docs.sqlbuild.com) for incremental models, scenarios, loaders, and more.

### Python project layout

Project-owned Python must live in a supported extension location such as `factories/`, `libs/`,
`macros/`, `providers/`, or another documented Python resource root. Factory locations contain
normal Python: constants, classes, undecorated helper functions, and modules such as `_helpers.py`
are allowed, while decorators determine which functions become SQLBuild resources. Compilation
rejects Python under invented project roots so indirectly importable modules cannot create an
unofficial project structure. Keep repository pytest tests outside the SQLBuild project's `tests/`
directory, which is reserved for SQLBuild SQL tests and scenarios. Documented integration paths
such as `dagster/`, `rivers_pipeline/`, and their `definitions.py` modules are also supported.

### Python macro declaration context

Python SQL macros receive the constants and enums visible to the SQL resource that calls them.
Use the typed mappings for Python control flow, and use the rendering methods when inserting a
declaration into generated SQL so quoting and collection syntax follow the active adapter:

```python
def minimum_order_filter(ctx) -> str:
    minimum = ctx.constants["minimum_order_value"]
    if minimum is None:  # The visible declaration explicitly has a NULL value.
        return "TRUE"
    return f"order_value >= {ctx.render_constant('minimum_order_value')}"


def active_status_filter(ctx) -> str:
    status = ctx.render_enum_member(enum_name="order_status", member_name="active")
    return f"status = {status}"
```

Callers can still pass explicit `@const(...)` or `@enum(...)` values as macro arguments. Context
lookups are intended for policy owned by the macro; both forms use the caller's declaration scope.

## Compiler-integrated Rules

Rules turn repeatable SQL and project review decisions into compile-time diagnostics. Mandatory
compiler correctness still runs first. SQLBuild then evaluates selected native built-ins, followed by
selected custom Python rules, before completing compile artifacts. `sqb compile` is authoritative;
build and execution commands enforce the same configuration. Rules report findings and never rewrite
SQL. `sqb format` remains a separate source-rewriting command.

Select rules in `sqlbuild_project.toml` by exact code or derived family prefix:

```toml
[rules]
select = ["SQBRSQL", "XSQBRARCH"]
ignore = ["SQBRSQL004"]
```

Built-in codes use `SQBR<FAMILY><three digits>`, such as `SQBRSQL001` and
`SQBRGRAPH101`. Custom codes use `XSQBR<optional family><three digits>`, such as
`XSQBRARCH001`. A family is always the code with its final three digits removed.

Custom rules are ordinary Python beneath `rules/**/*.py`. Only `@rule` functions register; helper
functions, constants, dataclasses, classes, and nested packages remain ordinary Python. Typed,
keyword-only parameters determine whether a rule runs once per model or once per project:

```python
from sqlbuild.rules import Finding, Model, RuleContext, rule


@rule(
    code="XSQBRARCH001",
    message="Final models must declare an order identifier",
    remediation="Declare order_id in the model contract.",
)
def final_order_identifier(*, model: Model, ctx: RuleContext) -> list[Finding]:
    declared = {column.name for column in ctx.columns.declared(model)}
    return [] if "order_id" in declared else [ctx.finding(subject=model)]
```

Use `Project` instead of `Model` for an invariant with no natural model subject. A model rule can
still inspect project-wide facts. `RuleContext` exposes compiler-owned SQL, graph, columns,
contracts, tests, audits, declarations, project metadata, and a deterministic project tree. Common
SQL facts are typed and lazy; the full Polyglot AST is an explicit escape hatch at
`ctx.sql.for_model(model).expanded.polyglot_ast()`.

Custom rules are deterministic and cacheable. Environment, network, subprocess, time, randomness,
and untracked filesystem access are rejected. Tracked project text must be read through
`ctx.project.tree`, and implementation, options, subject facts, helper code, project observations,
and backend compatibility participate in cache identity.

Inspect and run focused selections with:

```bash
sqb rules list
sqb rules show SQBRSQL001
sqb rules run SQBRSQL
sqb rules run XSQBRARCH --select customer_orders
sqb rules skills --check
```

Test custom rules through the real discovery and compiler path with `RuleCase` and `evaluate_rule`
from `sqlbuild.rules.testing`.

The neutral large-project benchmark supports 1,000, 3,000, 5,000, and 10,000-model profiles and
reports repeated median/p95 timings with cache accounting and phase breakdowns:

```bash
uv run python -m scripts.benchmark_rules --models 3000 --iterations 5
uv run python -m scripts.benchmark_rules --models 5000 --iterations 5
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
query IDs are stored under `target/executions/<run_id>/`; that statement ledger stores only an SQL
digest, not SQL text. Executed SQL artifacts are stored separately under the sensitive
`target/run/` tree.

## Documentation

Full documentation is available at [docs.sqlbuild.com](https://docs.sqlbuild.com).

Runtime operator and extension contracts:

- [Execution observability and local troubleshooting](docs/execution-observability.md)
- [SQLite and PostgreSQL execution history](docs/execution-history.md)
- [Typed lifecycle and command-output sinks](docs/sinks.md)

## Contributing

We welcome contributions. Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

SQLBuild is licensed under the [Apache License 2.0](LICENSE).
