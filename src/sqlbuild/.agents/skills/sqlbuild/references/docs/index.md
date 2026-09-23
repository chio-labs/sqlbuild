<!-- generated-by: sqlbuild skills -->

# Introduction

> Verify early, test properly, and deploy reversibly. SQL pipelines with the rigor of real software - free and open source.

Online: https://docs.sqlbuild.com/index

## Contents

- Test properly
- Verify early
- Plans that explain every build
- Deploy reversibly (opt-in)
- Supported adapters
- More in SQLBuild
- What's next
- Quick links

**Valid isn't the same as correct.** Your SQL compiles, runs, and returns rows - none of that means the number is right, and a silently-wrong number a stakeholder already trusted is the bug that actually hurts.

SQLBuild brings software-engineering rigor to SQL pipelines: **verify early, test properly, deploy reversibly.** Catch errors before the warehouse runs them and test your logic locally - with change-aware builds and reversible deploys there when you need them, not forced on you on day one. It is a standalone framework for building SQL and Python data pipelines - free and open source.

## Test properly

Most data testing checks for nulls and uniqueness. That tells you a column isn't empty, not that your logic is right. SQLBuild tests the logic.

- **Multi-model tests.** Mock your sources, assert on the model you care about, and SQLBuild resolves every intermediate model from its real SQL. One test file can cover a whole stretch of your pipeline.
- **E2E scenario tests with local replay.** Build the real model graph against coherent fixtures in isolated relations, capture the result as JSONL, and replay it locally through DuckDB. CI runs full end-to-end tests with zero warehouse credentials or compute.
- **Macro-powered mocks.** Tests are SQL, so they support macro calls - write reusable mock generators instead of copy-pasting fixtures.

```sql
-- Mock two sources, assert on the final mart.
-- stg_orders and stg_payments resolve automatically from their real SQL.
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
  SELECT
    1 AS order_id,
    100 AS customer_id,
    1500 AS total_cents,
    'credit_card' AS payment_method
)
SELECT 1
```

See [Testing](concepts/testing.md) for SQL unit tests and [Scenarios](concepts/scenarios.md) for local
E2E replay.

## Verify early

Before any model runs, SQLBuild does static analysis of your project - offline, no warehouse connection needed.

- **Catch errors at compile.** SQL syntax, type inference, contract checks, and column lineage all run before execution. A bad reference or a type mismatch fails at compile, with an error that points at the line - not halfway through a warehouse run.
- **Turn review decisions into compiler checks.** Configure [Rules](concepts/rules.md) over compiler-owned SQL, models, dependencies, contracts, tests, and project paths.
- **Format separately.** `sqb format` owns deterministic source rewriting; Rules remain diagnostic-only.
- **Fast, because it's Rust where it counts.** Static analysis runs on [Polyglot](https://github.com/tobilg/polyglot), a Rust SQL engine (MIT, 32+ dialects), so compile stays quick even on large projects.
- **Open, not paywalled.** The static analysis is part of the Apache-2.0 core - no proprietary engine, no separate login, and no paid tier gating the smart checks.

## Plans that explain every build

**Start simple.** By default, `sqb build` runs your full selection - the same predictable mental model as dbt, with nothing to configure. For many projects, that is all they will ever need.

Every model, seed, function, and Python node has a versioned identity. SQLBuild uses those identities
to explain query and configuration changes, propagate upstream changes, choose incremental replay
actions, and protect scoped builds from stale dependencies. Direct mode still runs the selected
scope; change detection makes that plan explicit rather than silently changing what was selected.

[Virtual environments](concepts/virtual-environments.md) add version reuse and optional stale-driven
execution when a project needs isolated previews, promotion, and rollback.

The planner carries that evidence across the whole graph:

- **Models and functions:** query, configuration, and dependency identities explain local and cascaded changes.
- **Seeds:** content and load-affecting configuration identify when a seed changed.
- **Audits:** audit evidence is associated with the model version it validated.
- **Source freshness:** observable source data versions can affect downstream plans, with lag tolerance to avoid jitter.
- **Cascade propagation:** when a model does change, the signal propagates downstream, with configurable replay windows (`replay_on_change`).
- **Python nodes:** source and dependency identities appear in plans; skip/run remains user-controlled through `ctx.skip()`.

In direct mode, this evidence is stored as append-only rows in your warehouse. Virtual environments
use their configured state backend for environment-scoped version bindings.

## Deploy reversibly (opt-in)

By default, SQLBuild runs in direct mode with state as append-only rows in your warehouse. When you want more, [virtual environments](concepts/virtual-environments.md) add a reversibility layer on top:

- **Instant branching, promotion, and rollback** as low-copy pointer operations.
- **Partial promotion.** Promote the models that are ready without re-running everything downstream of them - you don't have to rebuild the whole closure to ship one fix.
- **Checkpoints and reconciliation** so a bad change is something you undo, not an incident.

Virtual environments are opt-in, not a tax you pay upfront - direct mode stays the default, so the floor stays low and you reach for them only when a workflow needs them.

## Supported adapters

SQLBuild works with **DuckDB, MotherDuck, Snowflake, BigQuery, Databricks, PostgreSQL, and SQL Server** today. Support for ClickHouse, Redshift, Trino, Spark, and Athena is on the way.

DuckDB runs entirely locally, so you can try SQLBuild and run full E2E tests without any warehouse credentials. Head to the [Quickstart](quickstart.md) to get a project running in minutes, or see [Adapters](concepts/adapters.md) for connection setup.

## More in SQLBuild

### Familiar SQL models

Models are SQL files with a `MODEL()` header and a `SELECT`. References to other models and sources use `__ref()` and `__source()`, and configuration, schema, and audits are declared inline in the header. If you know dbt or SQLMesh, you already know the shape.

```sql
-- models/marts/fact_orders.sql
MODEL (
  materialized table,
  columns (
    order_id (audits [not_null, unique]),
  ),
);

SELECT
  o.order_id,
  o.customer_id,
  p.amount_cents AS total_cents,
  p.method AS payment_method
FROM __ref("stg_orders") o
JOIN __ref("stg_payments") p USING (order_id)
```

### Python macros, not Jinja

- **Real Python functions:** Macros are plain Python, called with `@macro()` in SQL. Testable, debuggable, and composable with standard tooling - no Jinja, no string-templating language to wrangle.

```python
# macros/grant_target.py
def grant_target(target):
    return f"GRANT SELECT ON {target} TO analyst_role"
```

### Audits that block bad data

- **Full table builds:** SQLBuild materializes into a staging table and runs `error`-severity audits before promotion. If any fail, the swap is blocked and the production table is untouched.
- **Incremental models:** Delta-phase audits validate each batch before DML is applied. Bad data is caught before it reaches the target.
- **Measured quality:** Measurement audits evaluate values against warning/error thresholds, distinguish insufficient samples, and can retain bounded evidence and immutable result history.

### Incremental processing

- **Cursor-based replay:** SQLBuild resumes by reading the highest timestamp or integer value already in the target table. If a model fails for several runs, the next successful build picks up from the last data it actually wrote, with no manual backfilling.
- **Microbatch mode:** Split large replay windows into configurable batches, each with its own audit cycle. Or process the full range in one pass, the choice is per-model.
- **Replay on change:** When a model's version identity changes, `replay_on_change` controls how much data to reprocess: `forward` (default, just run the next delta), `bounded-14d` (replay a window), or `full` (rebuild the table).

### Python you can read and extend

- **The framework is Python.** Adapters, macros, hooks, providers, custom materializations, and Python nodes are all plain Python you can read and extend. (The SQL analysis underneath runs on Rust via Polyglot - see [Verify early](#verify-early) - so the code you work with stays Python while compile stays fast.)

### Testing in depth

Beyond the multi-model tests shown above, SQLBuild runs end-to-end scenario tests against the real model graph, with local replay and property assertions.

- **Real graph execution:** Define coherent fixture inputs, and SQLBuild builds the real model graph against them in isolated warehouse relations. Test end-to-end business logic across your entire pipeline, not just one model at a time.
- **Local replay without a warehouse:** Capture scenario fixtures as JSONL snapshots, then replay them locally through DuckDB. CI pipelines run full E2E tests with zero warehouse credentials or compute cost.
- **Zero-row assertions:** Write property checks that pass when no rows violate a condition. Useful for invariants like "no negative revenue" or "no duplicate customer IDs" alongside full expected-output comparisons.

```sql
SCENARIO (
  description "Daily revenue includes only successful payments",
  tags ["revenue"]
);

WITH
__ref__stg_orders AS (
  SELECT 1 AS order_id, 10 AS customer_id, 'completed' AS status
),
__ref__stg_payments AS (
  SELECT
    1 AS payment_id,
    1 AS order_id,
    1700 AS amount_cents,
    'success' AS payment_status
),
__expected__daily_revenue AS (
  SELECT
    CAST('2026-04-01' AS DATE) AS revenue_date,
    1700 AS total_revenue_cents
),
__assert__all_orders_have_payments AS (
  SELECT * FROM __ref("fact_orders") WHERE payment_amount_cents IS NULL
)
SELECT 1
```

### Python nodes

Grow beyond warehouse-only SQL without leaving the graph. Python nodes are ordinary functions, decorated to become first-class nodes in the same DAG as your SQL models, and they run as part of `sqb build`. There are four kinds:

- **Loaders** (`@loader`) load external data into managed sources, with incremental write strategies (table, append, delete_insert, merge), cursor-based loading, and concurrent execution.
- **Tasks** (`@task`) run Python computation or side effects as graph nodes.
- **Assets** (`@asset`) produce or observe external artifacts, with optional columns and lineage.
- **Checks** (`@check`) validate tasks, assets, and loaders, and run during `sqb build` or on their own with `sqb check`.

```python
from sqlbuild.loaders import loader
from sqlbuild.executor.load.models import LoaderContext

@loader
def raw_orders(ctx: LoaderContext):
    if ctx.current_cursor_value is None:
        return fetch_all_orders()
    return fetch_orders_since(ctx.current_cursor_value)
```

SQL models never depend on Python nodes - the only path from Python into SQL is a loader populating a source - so the SQL graph stays fully analyzable on its own. Nodes can also be generated programmatically with `@factory`. See [Python Nodes](concepts/python-nodes/overview.md).

### Multi-target workflows

- **Data diffs:** Compare schemas and row-level data between targets (or virtual environments) with `sqb diff prod:dev`.

- **Zero-copy cloning:** Branch targets instantly with `sqb clone` without duplicating data.
- **Deferred references:** Resolve a production namespace with `--defer-to` through the active target's connection while building in dev.
- **No manifest required:** Clone, diff, and defer work directly against live targets. No `manifest.json` generation, no artifact management, no stale state.

### Extensibility

- **User-defined functions:** SQL and Python UDFs managed as part of your project. Functions participate in the DAG - definition changes trigger rebuilds of dependent models. Table functions provide predicate-pushdown-friendly alternatives to final-layer views.
- **Custom materializations:** Write materialization logic in Python with full framework integration - including audit hooks, schema change signals, and query change detection.

```python
def materialize(ctx: MaterializationContext) -> MaterializationResult:
    stale = find_untracked_partitions(ctx)

    for partition in stale:
        ctx.adapter.create_table_as(ctx.connection, target=staging, sql=partition_sql)
        ctx.run_audits(staging)  # same audit guarantees as built-in types
        ctx.execute_sql(f"INSERT INTO {ctx.destination} SELECT * FROM {staging}")

    return MaterializationResult(relation=ctx.destination)
```
- **Path-between selectors:** `--select fact_orders~daily_activity_rollup` selects every model on the shortest path between two nodes, with optional upstream/downstream expansion.

## What's next

- **Broader adapter support** - ClickHouse, Redshift, Trino, Spark, Athena

## Quick links

    Get a project running locally in minutes.
    Reference for SQLBuild commands and flags.
    Understand models, incremental strategies, audits, and selectors.
    E2E tests with local DuckDB replay.
