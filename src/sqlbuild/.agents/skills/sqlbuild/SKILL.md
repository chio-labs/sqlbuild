---
name: sqlbuild
description: Use when working with SQLBuild syntax, project structure, configuration, testing, adapters, CLI behavior, SQLBuild docs, or SQLBuild-related code.
---

<!-- generated-by: sqlbuild skills -->

# SQLBuild Skill

This file is generated from the SQLBuild documentation. Use it as the source of truth for SQLBuild syntax, project structure, configuration, testing, adapters, and CLI behavior.

## Included Pages

- `index`
- `quickstart`
- `feature-comparison`
- `concepts/dbt-compatibility/overview`
- `concepts/dbt-compatibility/selection`
- `concepts/dbt-compatibility/adding-sqlbuild-models`
- `concepts/project-configuration`
- `concepts/resource-identities`
- `concepts/adapters`
- `concepts/adapters/duckdb`
- `concepts/adapters/motherduck`
- `concepts/adapters/snowflake`
- `concepts/adapters/bigquery`
- `concepts/adapters/databricks`
- `concepts/adapters/postgres`
- `concepts/adapters/sqlserver`
- `concepts/sources`
- `concepts/seeds`
- `concepts/models`
- `concepts/models/materializations`
- `concepts/models/schemas`
- `concepts/models/type-enforcement`
- `concepts/models/contracts`
- `concepts/models/hooks`
- `concepts/models/hooks/sql`
- `concepts/models/hooks/python`
- `concepts/models/configuration`
- `concepts/enums`
- `concepts/constants`
- `concepts/constants/collections-and-rendering`
- `concepts/enums/model-contracts`
- `concepts/model-private-values`
- `concepts/macros`
- `concepts/macros/composition-and-context`
- `concepts/interpolation`
- `concepts/functions`
- `concepts/incremental`
- `concepts/planning`
- `concepts/planning/cascade-propagation`
- `concepts/planning/source-freshness`
- `concepts/planning/selection-and-staleness`
- `concepts/snapshots`
- `concepts/audits`
- `concepts/testing`
- `concepts/scenarios`
- `concepts/selectors`
- `concepts/column-lineage`
- `concepts/diff`
- `concepts/declaration-scopes`
- `concepts/declaration-scopes/visibility`
- `concepts/declaration-scopes/placement`
- `concepts/declaration-scopes/explorer`
- `concepts/kata`
- `concepts/kata/custom-rules`
- `concepts/python-nodes/overview`
- `concepts/python-nodes/loaders`
- `concepts/python-nodes/tasks`
- `concepts/python-nodes/assets`
- `concepts/python-nodes/checks`
- `concepts/python-nodes/factories`
- `concepts/python-nodes/providers`
- `concepts/python-nodes/sql-references`
- `concepts/virtual-environments`
- `concepts/virtual-environments/setup`
- `concepts/virtual-environments/building`
- `concepts/virtual-environments/promotion`
- `concepts/virtual-environments/rollback`
- `concepts/virtual-environments/adopt-detach`
- `concepts/virtual-environments/clone`
- `concepts/virtual-environments/diff`
- `concepts/virtual-environments/reconcile`
- `concepts/virtual-environments/locks`
- `concepts/virtual-environments/janitor`
- `concepts/virtual-environments/recovery`
- `integrations/dagster`
- `integrations/dagster-reference`
- `integrations/rivers`
- `integrations/dlt`
- `integrations/ingestr`
- `cli/init`
- `cli/playground`
- `cli/skills`
- `cli/compile`
- `cli/scope`
- `cli/kata`
- `cli/plan`
- `cli/build`
- `cli/load`
- `cli/seed`
- `cli/test`
- `cli/scenario`
- `cli/audit`
- `cli/freshness`
- `cli/check`
- `cli/clone`
- `cli/diff`
- `cli/lineage`
- `cli/dag`
- `cli/query`
- `cli/debug`
- `cli/janitor`
- `cli/clean`
- `cli/dbt`
- `cli/state`
- `cli/promote`
- `cli/rollback`
- `cli/reconcile`
- `concepts/enums-and-constants`

## Introduction

Source: `index.mdx`

Verify early, test properly, and deploy reversibly. SQL pipelines with the rigor of real software - free and open source.

**Valid isn't the same as correct.** Your SQL compiles, runs, and returns rows - none of that means the number is right, and a silently-wrong number a stakeholder already trusted is the bug that actually hurts.

SQLBuild brings software-engineering rigor to SQL pipelines: **verify early, test properly, deploy reversibly.** Catch errors before the warehouse runs them and test your logic locally - with change-aware builds and reversible deploys there when you need them, not forced on you on day one. It is a standalone framework for building SQL and Python data pipelines - free and open source.

### Test properly

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

See [Testing](/concepts/testing) for SQL unit tests and [Scenarios](/concepts/scenarios) for local
E2E replay.

### Verify early

Before any model runs, SQLBuild does static analysis of your project - offline, no warehouse connection needed.

- **Catch errors at compile.** SQL syntax, type inference, contract checks, and column lineage all run before execution. A bad reference or a type mismatch fails at compile, with an error that points at the line - not halfway through a warehouse run.
- **Enforce architecture deliberately.** Opt into [Kata](/concepts/kata) to check model structure, dependency CTEs, layer boundaries, joins, naming, contracts, and test coverage with coded faults and remediations.
- **Fast, because it's Rust where it counts.** Static analysis runs on [Polyglot](https://github.com/tobilg/polyglot), a Rust SQL engine (MIT, 32+ dialects), so compile stays quick even on large projects.
- **Open, not paywalled.** The static analysis is part of the Apache-2.0 core - no proprietary engine, no separate login, and no paid tier gating the smart checks.

### Change-aware builds, when you need them

**Start simple.** By default, `sqb build` runs your full selection - the same predictable mental model as dbt, with nothing to configure. For many projects, that is all they will ever need.

**Scale deliberately.** Change-aware builds are powerful: every model, seed, UDF, and Python node has a versioned identity, so SQLBuild can skip anything already current and only pay for the work that actually changed. But that power introduces complexity - warehouse state to reason about, staleness and cascade behavior, and partial-selection edge cases - that is not worth it for smaller or simpler pipelines. So it is opt-in and part of [virtual environments](/concepts/virtual-environments): turn it on with `--changes-only` (or `changes_only = true` in config) when the cost of full rebuilds outgrows the simplicity of running everything.

When enabled, change detection covers the whole graph:

- **Models and UDFs:** fingerprinted by query hash, config, and upstream UDF hashes. Unchanged models are skipped.
- **Seeds:** content and load-affecting config are hashed. Unchanged seeds are not reloaded.
- **Audits:** audits that already passed for the same model version are not re-run.
- **Source freshness:** external source data versions are tracked automatically. Models downstream of unchanged sources are skipped, with lag tolerance to avoid jitter.
- **Cascade propagation:** when a model does change, the signal propagates downstream, with configurable replay windows (`replay_on_change`).
- **Python nodes:** loaders, tasks, assets, checks, and hooks are fingerprinted by source and dependency hashes; skip/run is user-controlled via `ctx.skip()`.

State is plain append-only rows in your own warehouse (`_sqlbuild_fingerprints`, `_sqlbuild_source_freshness`, `_sqlbuild_node_results`) - no external state database, no manifest files, no state machine that can corrupt.

### Deploy reversibly (opt-in)

By default, SQLBuild runs in direct mode with state as append-only rows in your warehouse. When you want more, [virtual environments](/concepts/virtual-environments) add a reversibility layer on top:

- **Instant branching, promotion, and rollback** as low-copy pointer operations.
- **Partial promotion.** Promote the models that are ready without re-running everything downstream of them - you don't have to rebuild the whole closure to ship one fix.
- **Checkpoints and reconciliation** so a bad change is something you undo, not an incident.

Virtual environments are opt-in, not a tax you pay upfront - direct mode stays the default, so the floor stays low and you reach for them only when a workflow needs them.

### Supported adapters

SQLBuild works with **DuckDB, MotherDuck, Snowflake, BigQuery, Databricks, PostgreSQL, and SQL Server** today. Support for ClickHouse, Redshift, Trino, Spark, and Athena is on the way.

DuckDB runs entirely locally, so you can try SQLBuild and run full E2E tests without any warehouse credentials. Head to the [Quickstart](/quickstart) to get a project running in minutes, or see [Adapters](/concepts/adapters) for connection setup.

### More in SQLBuild

#### Familiar SQL models

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

#### Python macros, not Jinja

- **Real Python functions:** Macros are plain Python, called with `@macro()` in SQL. Testable, debuggable, and composable with standard tooling - no Jinja, no string-templating language to wrangle.

```python
# macros/grant_target.py
def grant_target(target):
    return f"GRANT SELECT ON {target} TO analyst_role"
```

#### Audits that block bad data

- **Full table builds:** SQLBuild materializes into a staging table and runs `error`-severity audits before promotion. If any fail, the swap is blocked and the production table is untouched.
- **Incremental models:** Delta-phase audits validate each batch before DML is applied. Bad data is caught before it reaches the target.

#### Incremental processing

- **Cursor-based replay:** SQLBuild resumes by reading the highest timestamp or integer value already in the target table. If a model fails for several runs, the next successful build picks up from the last data it actually wrote, with no manual backfilling.
- **Microbatch mode:** Split large replay windows into configurable batches, each with its own audit cycle. Or process the full range in one pass, the choice is per-model.
- **Replay on change:** When a model's version identity changes, `replay_on_change` controls how much data to reprocess: `forward` (default, just run the next delta), `bounded-14d` (replay a window), or `full` (rebuild the table).

#### Python you can read and extend

- **The framework is Python.** Adapters, macros, hooks, providers, custom materializations, and Python nodes are all plain Python you can read and extend. (The SQL analysis underneath runs on Rust via Polyglot - see [Verify early](#verify-early) - so the code you work with stays Python while compile stays fast.)

#### Testing in depth

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

#### Python nodes

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

SQL models never depend on Python nodes - the only path from Python into SQL is a loader populating a source - so the SQL graph stays fully analyzable on its own. Nodes can also be generated programmatically with `@factory`. See [Python Nodes](/concepts/python-nodes/overview).

#### Multi-target workflows

- **Data diffs:** Compare schemas and row-level data between targets (or virtual environments) with `sqb diff prod:dev`.

- **Zero-copy cloning:** Branch targets instantly with `sqb clone` without duplicating data.
- **Deferred references:** Resolve a production namespace with `--defer-to` through the active target's connection while building in dev.
- **No manifest required:** Clone, diff, and defer work directly against live targets. No `manifest.json` generation, no artifact management, no stale state.

#### Extensibility

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

### What's next

- **Broader adapter support** - ClickHouse, Redshift, Trino, Spark, Athena

### Quick links

    Get a project running locally in minutes.
    Reference for SQLBuild commands and flags.
    Understand models, incremental strategies, audits, and selectors.
    E2E tests with local DuckDB replay.

## Quickstart

Source: `quickstart.mdx`

Get a SQLBuild project running locally with DuckDB in under a minute.

This guide walks you through creating and running a complete transformation project - views, tables, incremental models, audits, tests, and a custom materialization - all running locally against DuckDB. No external data setup or warehouse credentials required.

### Prerequisites

- Python 3.12+
- SQLBuild installed: `uv pip install sqlbuild` or `pip install sqlbuild`

### 1. Create the playground

```bash
sqb playground waffle-shop
cd waffle-shop
```

This creates a self-contained waffle shop project with everything you need to explore SQLBuild.

The playground creates the shared `sqlbuild_project.toml`; that is sufficient for this
quickstart. In a team project, you can additionally create a gitignored
`sqlbuild_local.toml` to select your usual target and override your personal development
schema or credentials without changing the committed project config. See
[Project Configuration](/concepts/project-configuration#sqlbuild_local-toml).

### 2. Plan

Preview what SQLBuild will do:

```bash
sqb plan
```

```
Plan ready (13 selected)

First run (12)
  stg_customers               view
  stg_payments                view
  stg_orders                  view
  daily_order_partitioned     partition_tracked (custom)
  daily_revenue               table
  dim_customers               table
  fact_orders                 table
  customer_status_snapshot    merge (timestamp)
  hourly_order_activity       delete_insert (timestamp, microbatch)
  daily_activity_rollup       delete_insert (timestamp, microbatch)
  hourly_activity_with_daily_context delete_insert (timestamp, microbatch)
  order_status_index          delete_insert (integer)

Seeds (1)
  waffle_types
```

Source data is defined as inline expressions in `sources/raw.yml`, so SQLBuild resolves everything at compile time - no seeding step needed.

### 3. Build

Execute the full build:

```bash
sqb --no-color build
```

SQLBuild materializes all models in DAG order. SQL unit tests run before their target models. Error-severity audits run against a staging table before promotion - if any fail, the production table is untouched:

```
Execution  sqb build  (concurrency: 1)

   1/13  seed      waffle_types                                          OK     0.09s
   2/13  view      stg_customers                                         OK     0.05s
           audit     not_null (customer_id)                              PASS
           audit     unique (customer_id)                                PASS
           audit     not_null (email)                                    PASS
   3/13  view      stg_payments                                          OK     0.02s
           audit     not_null (payment_id)                               PASS
           audit     unique (payment_id)                                 PASS
           audit     not_null (order_id)                                 PASS
   4/13  view      stg_orders                                            OK     0.03s
           test      test_stg_orders                                     PASS
           audit     not_null (order_id)                                 PASS
           audit     unique (order_id)                                   PASS
           audit     not_null (customer_id)                              PASS
           audit     accepted_values (status)                            PASS
   5/13  custom    daily_order_partitioned                               OK     0.17s
           audit     expression_is_true                                  PASS  4/4
           audit     not_null (order_date)                               PASS  4/4
   6/13  table     daily_revenue                                         OK     0.05s
           audit     expression_is_true                                  PASS
   7/13  table     dim_customers                                         OK     0.05s
           audit     not_null (customer_id)                              PASS
           audit     unique (customer_id)                                PASS
   8/13  table     fact_orders                                           OK     0.04s
           audit     not_null (order_id)                                 PASS
   9/13  table     customer_status_snapshot  (merge)                     OK     0.04s
           audit     not_null (customer_id)                              PASS
           audit     unique (customer_id)                                PASS
  10/13  table     hourly_order_activity  (delete_insert)                OK     0.16s
           audit (d) expression_is_true                                  PASS  4/4
           audit (d) not_null (activity_hour)                            PASS  4/4
           audit (f) expression_is_true                                  PASS
           audit (f) not_null (activity_hour)                            PASS
  11/13  table     order_status_index  (delete_insert)                   OK     0.03s
           audit     not_null (order_id)                                 PASS
           audit     unique (order_id)                                   PASS
  12/13  table     daily_activity_rollup  (delete_insert)                OK     0.08s
           audit (d) expression_is_true                                  PASS  2/2
           audit (d) not_null (activity_day)                             PASS  2/2
           audit (f) expression_is_true                                  PASS
           audit (f) not_null (activity_day)                             PASS
  13/13  table     hourly_activity_with_daily_context  (delete_insert)   OK     0.17s
           audit (d) expression_is_true                                  PASS  4/4
           audit (d) not_null (activity_hour)                            PASS  4/4
           audit (f) expression_is_true                                  PASS
           audit (f) not_null (activity_hour)                            PASS

Completed successfully.
PASS=66  WARN=0  FAIL=0  SKIP=0  TOTAL=66  (1.09s)
```

Notice `audit (d)` and `audit (f)` on incremental models - these are delta-phase and final-phase audits. Delta audits validate each batch before DML is applied; final audits run against the target after promotion.

### 4. Verify

Run the plan again to see the steady-state:

```bash
sqb plan
```

```
Plan ready (13 selected)

Normal (12)
    3 view
    3 table
    3 delete_insert (timestamp, microbatch)
    1 partition_tracked (custom)
    1 merge (timestamp)
    1 delete_insert (integer)

Seeds (1)
  waffle_types
```

All models now show `Normal` instead of `First run`.

### 5. Common operations

```bash
# Rebuild a specific model
sqb build --select daily_revenue

# Rebuild models under a path
sqb build --select path:models/marts

# Full refresh of everything
sqb build --full-refresh

# Run tests only
sqb test

# Run audits only
sqb audit

# Inspect lineage
sqb lineage fact_orders --direction both

# Compile and check contracts
sqb compile
```

### What you just built

#### Model DAG

```
raw__customers ──> stg_customers ──> dim_customers
raw__orders ────> stg_orders ────> fact_orders ──> customer_status_snapshot
raw__payments ──> stg_payments ──>  │              order_status_index
                                   │              hourly_order_activity ──> daily_activity_rollup
                                   │                                       hourly_activity_with_daily_context
                                   └──> daily_revenue
                                   └──> daily_order_partitioned
```

#### Materialization types

The project demonstrates several materialization strategies:

- **Views** (`stg_customers`, `stg_orders`, `stg_payments`) - lightweight staging layer
- **Tables** (`fact_orders`, `dim_customers`, `daily_revenue`) - full table rebuilds
- **Merge incremental** (`customer_status_snapshot`) - upsert with timestamp cursor
- **Delete/insert incremental** (`hourly_order_activity`, `daily_activity_rollup`, `hourly_activity_with_daily_context`) - microbatch processing with configurable batch sizes
- **Integer cursor incremental** (`order_status_index`) - non-timestamp incremental
- **Custom materialization** (`daily_order_partitioned`) - Python-defined partition-tracked strategy

See [Incremental](/concepts/incremental) for details on cursor-based strategies and microbatch processing.

#### Project structure

```
waffle-shop/
  sqlbuild_project.toml         # project config
  sources/
    raw.yml                     # source declarations (inline expression data)
  seeds/
    waffle_types.csv            # seed data
    lookups.yml                 # seed declarations
  functions/
    sql/
      udf__is_completed_order.sql    # scalar SQL UDF
      table_fn__customer_orders.sql  # table function
  schemas/
    orders/
      order.sql                 # reusable model column schema
  models/
    staging/
      stg_customers.sql         # view (audits declared in MODEL() header)
      stg_orders.sql            # view
      stg_payments.sql          # view
    marts/
      fact_orders.sql           # table
      dim_customers.sql         # table
      daily_revenue.sql         # table
      daily_order_partitioned.sql # custom materialization
      hourly_order_activity.sql # microbatch incremental
      hourly_activity_with_daily_context.sql # microbatch incremental
      daily_activity_rollup.sql # microbatch incremental
    intermediate/
      customer_status_snapshot.sql  # merge incremental
      order_status_index.sql       # integer cursor incremental
  audits/
    generic/
      expression_is_true.sql    # custom generic audit
  tests/
    unit/
      test_stg_orders.sql              # model unit test
      test_fact_orders.sql             # multi-model test
      test_daily_revenue_chain.sql     # multi-model test
      test_line_total_cents_macro.sql  # macro test
    scenarios/
      daily_revenue_minimal.sql   # E2E scenario test
      daily_revenue_multi_order.sql # E2E scenario test
  macros/
    currency.py                 # cents_to_dollars macro
    datetime.py                 # adapter-portable timestamp_trunc
  materializations/
    partition_tracked.py        # custom materialization
```

### Next steps

- [Models](/concepts/models) - understand `MODEL()` headers and materialization types
- [Kata](/concepts/kata) - opt into repository architecture and model-shape checks
- [Functions](/concepts/functions) - SQL UDFs, Python UDFs, and table functions
- [Incremental](/concepts/incremental) - learn about cursor-based incremental strategies
- [Audits](/concepts/audits) - configure data quality checks
- [Testing](/concepts/testing) - write SQL unit tests and multi-model tests with macro support
- [Column Lineage](/concepts/column-lineage) - trace individual columns through your pipeline
- [CLI Reference](/cli/build) - full command reference

## Feature Comparison

Source: `feature-comparison.mdx`

Feature comparison between SQLBuild, dbt, and SQLMesh.

SQLBuild, dbt, and SQLMesh are all SQL pipeline frameworks. They share common ground but differ in design philosophy and feature focus.

### Feature comparison

#### Testing

| Feature | SQLBuild | dbt | SQLMesh |
|---------|----------|-----|---------|
| Multi-model tests | Chain across multiple models | YAML-stub, single model | CTE-based, single model |
| Typed parameterized unit tests | Independent named cases with adapter-rendered scalar values | No | No |
| Macros as test helpers | Tests are SQL - macros work as reusable fixture generators | No (YAML stubs) | No |
| E2E scenario tests | Fixture worlds with real graph execution | No | No |
| Local E2E replay | Capture from warehouse, replay in DuckDB | No | No |
| Macro / UDF / table function tests | `TEST(mode macro)`, `TEST(mode udf)`, or `TEST(mode table_fn)` | No | No |
| Zero-row assertions | `__assert__` CTEs in tests and scenarios | No | No |

#### Audits

| Feature | SQLBuild | dbt | SQLMesh |
|---------|----------|-----|---------|
| Built-in audits | not_null, unique, accepted_values, relationships | not_null, unique, accepted_values, relationships | Extensive (statistical, string pattern, etc.) |
| Blocking audits | Block promotion from staging table | Tests run after materialization | Audits gate plan application; run-time audits execute after the interval is materialized |
| Delta/interval-scoped audits | Per-microbatch audit cycle before DML | No | Audit query filtered to processed intervals for time-range models |

#### Compilation

| Feature | SQLBuild | dbt | SQLMesh |
|---------|----------|-----|---------|
| SQL validation | Offline, compile-time (Polyglot) | dbt Core: none; dbt Fusion engine: compile-time (proprietary; built on Apache-2.0 dbt Core v2) | Compile-time (SQLGlot) |
| Column-level lineage | Compile-time, fast and rich modes | dbt Core: post-hoc via docs; dbt Fusion engine: compile-time | Compile-time |
| Column contract validation | Compile-time inference plus runtime enforcement with `contract enforced` | YAML schema contracts at runtime | Schema contracts via plan |
| SQL architecture policy | Opt-in Kata rules over compiled models with coded faults, remediations, suppressions, and custom rules | Project conventions through packages and external tooling | Built-in audits and external linting |
| SQL transpilation | For local E2E replay into DuckDB | No | For cross-dialect model execution |
| Python macros | `@macro()` syntax | No (Jinja only) | SQLMesh macro syntax |
| Compiler-enforced declaration scopes | Project, descendant-public, exact-owner-private, and model-private tiers with offline `sqb scope` inspection | No lexical declaration scopes | No lexical declaration scopes |
| Jinja support | No (Python macros instead) | Yes (core templating) | Yes |

#### Incremental

| Feature | SQLBuild | dbt | SQLMesh |
|---------|----------|-----|---------|
| Incremental strategies | append, delete_insert, merge, SCD Type 2 | append, delete_insert, merge, snapshots | delete_insert (time-range), merge (unique-key), SCD Type 2, partition |
| Microbatch execution | Configurable batch sizes with per-batch audits | Microbatch (recent addition) | Batch size support |
| Stateful interval tracking | Cursor-based, no external interval state | No | Tracks which intervals have run (in state store) |
| SCD Type 2 models | Timestamp and check strategies, historical input, hard deletes | Snapshots (timestamp and check strategies) | `SCD_TYPE_2` model kind (timestamp and check strategies) |

#### Planning and change detection

| Feature | SQLBuild | dbt | SQLMesh |
|---------|----------|-----|---------|
| Change-aware builds | Opt-in (`--changes-only`) in virtual environments; fingerprints models, seeds, functions, Python nodes and skips unchanged work including audits | dbt State (paid) | Version hash comparison |
| Warehouse-native state | Append-only tables in the warehouse; no external state database | manifest.json artifacts | Requires external state store (SQLite/PostgreSQL) |
| Source freshness | `sqb freshness` with adapter/column/sql strategies, lag tolerance, and CI gating | `dbt source freshness` | No dedicated freshness command; `signals` gate model evaluation until external data is ready |
| Reuse across environments | Virtual environments reuse fingerprint-matched physical tables across environments (shared physical storage) | dbt State clone (paid) | Virtual environments reuse fingerprint-matched physical tables across environments (shared physical storage) |
| Cascade propagation | Topological walk with `replay_on_change` policy inheritance and override | No cascade control | Cascades through version hashes |

#### Environments

| Feature | SQLBuild | dbt | SQLMesh |
|---------|----------|-----|---------|
| Virtual environments | Pointer swaps with hash-based version reuse (opt-in) | No | Pointer swaps, no compute cost |
| Data diffs | Full row-level data comparison across targets or virtual environments | No | Table diff |
| Zero-copy cloning | `sqb clone` | No | No |

#### Models

| Feature | SQLBuild | dbt | SQLMesh |
|---------|----------|-----|---------|
| SQL models | `MODEL()` header with inline config | Jinja-templated SQL + YAML sidecar | `MODEL` DDL |
| Python models | Coming soon | Pandas, PySpark, Snowpark, BigFrames | Pandas, PySpark, Snowpark, BigFrames |
| Custom materializations | Python with full framework hooks | Jinja-based | Python-based custom model kinds |
| Lifecycle hooks | Typed inline SQL, reusable parameterized SQL resources, and Python hooks with compile-time validation and `HookContext` | Jinja pre/post hooks | Python pre/post hooks |

#### Python nodes

| Feature | SQLBuild | dbt | SQLMesh |
|---------|----------|-----|---------|
| Tasks | `@task` - Python computation as DAG nodes | No | No |
| Assets | `@asset` - external artifact production/observation | No | No |
| Checks | `@check` - Python validation of tasks, assets, and loaders | No | No |
| Factories | `@factory` - programmatic node generation | No | No |
| Providers | Shared runtime services with name-based injection into nodes and hooks | No | No |

#### dbt interoperability

| Feature | SQLBuild | dbt | SQLMesh |
|---------|----------|-----|---------|
| dbt compatibility | Reads dbt manifests, coordinates dbt and SQLBuild selection, and supports SQLBuild models downstream | N/A | Jinja compatibility layer plus own macro system |

#### Sources

| Feature | SQLBuild | dbt | SQLMesh |
|---------|----------|-----|---------|
| Source loaders | Python `@loader` functions with table/append/delete_insert/merge strategies | No (external to dbt) | No (external to SQLMesh) |
| Declarative ingestion | dlt and ingestr integrations - YAML-only source config, no Python | No | No |
| Auto-load during builds | Managed sources loaded before dependent models | No | No |
| Source deferral | `--defer-sources-to` reads source data from another target | No | No |

#### Other

| Feature | SQLBuild | dbt | SQLMesh |
|---------|----------|-----|---------|
| Reference syntax | `__ref()` - parses as valid SQL | `{{ ref() }}` - Jinja template | `model_name` with dependency tracking |
| Adapters | DuckDB, MotherDuck, Snowflake, BigQuery, Databricks, PostgreSQL, SQL Server | 30+ (community adapters) | DuckDB, Snowflake, BigQuery, Databricks, Spark, Redshift, Postgres, Trino, MySQL |
| State requirements | Stateless by default | manifest.json + target/ | Requires state store (local database or PostgreSQL for production) |
| Playground | `sqb playground` | Clone example repo | Example project |
| AI agent skills | General guidance with `sqb skills`; policy-derived guidance with `sqb kata skills` | No | No |

### Where each tool fits

| Tool | Best for |
|------|----------|
| **SQLBuild** | Rigor-first SQL pipelines: compile-time verification, pre-promotion audit gating, multi-model tests, and local E2E replay by default. Opt into change-aware builds and warehouse-native state when full rebuilds get expensive, plus ingestion, Python nodes, and virtual environments as the project grows. |
| **dbt** | The most widely adopted SQL transformation framework with the largest adapter and community ecosystem. |
| **SQLMesh** | State-managed pipelines with virtual environments, interval tracking, and cross-dialect transpilation. |

### Not yet in SQLBuild

- **Broader adapter support** - ClickHouse, Redshift, Trino, Spark, Athena

## Using SQLBuild with dbt

Source: `concepts/dbt-compatibility/overview.mdx`

Run dbt and SQLBuild side by side with coordinated selection and SQLBuild models downstream.

Use the dbt compatibility bridge to coordinate dbt selections with SQLBuild-owned models downstream of their outputs.

SQLBuild reads the dbt manifest and drives the `dbt` CLI as a subprocess. dbt remains responsible for compiling and executing dbt-owned models; SQLBuild statically analyzes and executes only SQLBuild-owned models downstream. `sqb dbt` runs in direct mode, so change-aware execution and virtual environments are not supported by the bridge.

### Start with your existing dbt project

From inside your dbt project, run a `sqb dbt` command. Scope dbt work with familiar `--select` values, or omit selection to plan the whole project.

```bash
sqb dbt plan --select path:models/marts
```

The first time you do this, SQLBuild bootstraps itself. If there is no `sqlbuild_project.toml`, it reads your `dbt_project.yml` and profile and creates a minimal twin project in a `sqlbuild_project/` directory next to your dbt project. It reuses your dbt profile for the warehouse connection, so there are no separate credentials to configure.

```
my-workspace/
  analytics/                  # your existing dbt project, untouched
    dbt_project.yml
    models/
    target/
      manifest.json
  sqlbuild_project/           # created by SQLBuild
    sqlbuild_project.toml     # points at the dbt project, no models of its own
```

The generated `sqlbuild_project.toml` looks like this:

```toml
name = "analytics"
adapter = "snowflake"
default_target = "dev"

[dbt]
project_dir = "../analytics"
profiles_dir = "/Users/you/.dbt"
target_path = "../analytics/target"
target = "dev"

[connections.dbt_dev]
source = "dbt_profile"
profile = "analytics"
target = "dev"

[targets.dev]
connection = "dbt_dev"
database = "ANALYTICS"
schema = "analytics"
```

`source = "dbt_profile"` on the named connection tells SQLBuild to connect using your dbt
profile, so it talks to the same warehouse dbt does. The target references that connection and
remains authoritative for its database and schema.

`sqb dbt build --select path:models/marts` compiles the project, resolves the selection, runs the selected dbt models, then runs any SQLBuild models you have added against the dbt outputs.

### How it works

1. SQLBuild runs `dbt compile` to produce a `manifest.json` with model metadata
2. SQLBuild reads the manifest to understand dbt model names and their qualified warehouse tables
3. SQLBuild resolves your `--select`/`--exclude` against dbt by running `dbt ls`, so dbt-native selectors like `state:modified` and `package:` are evaluated by dbt itself, not reimplemented
4. `sqb dbt plan/run/build` orchestrates the run: dbt executes the selected dbt work
5. (Optional) any SQLBuild models you have added run last, against the dbt outputs

Each step calls the `dbt` CLI directly: `dbt compile` for the manifest, `dbt ls` for selection, and `dbt build`/`dbt run` for execution.

#### Flags

`sqb dbt plan/run/build` declare the common flags directly. Anything declared goes **before** a `--` separator; any other raw dbt flag goes **after** it and is forwarded verbatim. A flag placed on the wrong side errors rather than silently reaching dbt.

```bash
sqb dbt build --select path:models/marts --full-refresh
```

Declared flags are routed to the right place automatically:

| Flag | Routed to | Notes |
| ---- | --------- | ----- |
| `--select` / `--exclude` | dbt | dbt resolves selection (see [Selection](/concepts/dbt-compatibility/selection)). |
| `--vars` | dbt **and** SQLBuild | The same vars feed dbt's compile and SQLBuild's own variable resolution, so both sides see identical values. |
| `--full-refresh` | dbt **and** SQLBuild | Requests a full rebuild on both sides. dbt and native SQLBuild models independently apply their model-level `full_refresh` setting, including `false` opt-outs. |
| `--threads` | dbt (`--threads`) and SQLBuild (`--concurrency`) | |
| `--target` / `--project-dir` / `--profiles-dir` / `--profile` / `--target-path` | dbt | Standard dbt locators. |

##### `--vars`

`--vars` accepts the same JSON object dbt accepts, and SQLBuild passes it to **both** the underlying `dbt` invocation and its own variable resolution. That means a value referenced as `@@my_var` in SQLBuild model SQL (see [Interpolation](/concepts/interpolation)) and as `{{ var('my_var') }}` in a dbt model both resolve to the value you passed. CLI vars take precedence over project and local config vars. You do not need to declare vars twice.

```bash
sqb dbt build --select path:models/marts --vars '{"my_var": 1}'
```

##### Forwarding other dbt flags

For any native dbt flag SQLBuild does not declare, put it after `--` and it is passed straight to the `dbt` invocation untouched:

```bash
sqb dbt build -- --log-level debug
```

### Configuration

The auto-generated project above is editable, and you can write `sqlbuild_project.toml` by hand. The `[dbt]` block (shown in the generated project above) accepts:

| Field | Description |
|-------|-------------|
| `project_dir` | Path to the dbt project root (where `dbt_project.yml` lives) |
| `profiles_dir` | Path to the directory containing `profiles.yml` |
| `target_path` | Path to dbt's `target/` directory (where `manifest.json` is written) |
| `target` | dbt target name override (optional) |

Paths can be absolute or relative to the SQLBuild project root.

### Prerequisites

- dbt must be installed and available on `PATH` as `dbt`
- Both projects must target the same warehouse and schema/database context

SQLBuild uses your own `dbt` install; it does not bundle or install dbt. If your `dbt` is not reachable as a bare `dbt` on `PATH` (for example, you run it via `uv`, `poetry`, or a wrapper), set the `DBT_EXECUTABLE` environment variable to the executable SQLBuild should call.

SQLBuild runs `dbt compile` automatically as part of `sqb dbt plan/run/build` to produce the manifest. You do not need to compile the dbt project manually.

### Debugging

`sqb dbt debug` runs both projects' diagnostics: `dbt debug` (verifying the dbt project config and warehouse connection) followed by `sqb debug` (verifying the SQLBuild project config and connection).

```bash
sqb dbt debug
```

### On this topic

- [Selection](/concepts/dbt-compatibility/selection) - how `--select` and `--exclude` route work across both graphs.
- [Adding SQLBuild models](/concepts/dbt-compatibility/adding-sqlbuild-models) - optionally write SQLBuild models, tests, audits, and scenarios downstream of dbt.

## Selection

Source: `concepts/dbt-compatibility/selection.mdx`

How select and exclude flags route work across the dbt and SQLBuild graphs.

The `sqb dbt` commands use `--select` and `--exclude` to scope what runs. Selectors work across both dbt and SQLBuild, with the system determining which side owns each selector and how to route work.

### SQLBuild-recognized selectors

These selectors match SQLBuild models directly:

| Selector | Example | Behavior |
|----------|---------|----------|
| Model name | `fact_orders` | Selects that SQLBuild model. Auto-includes its immediate dbt upstream dependencies. |
| Leading `+` | `+fact_orders` | Selects the model plus walks upstream through both SQLBuild and dbt models. |
| Trailing `+` | `fact_orders+` | Selects the model plus all downstream SQLBuild models. |
| Both `+` | `+fact_orders+` | Full upstream (including dbt) and downstream expansion. |
| Tag | `tag:nightly` | Selects all SQLBuild models with that tag. Auto-includes dbt dependencies. |
| Tag with `+` | `+tag:nightly` | Tag match plus upstream expansion through the combined graph. |
| Path | `path:models/marts` | Selects SQLBuild models under that project-relative directory - the same syntax as dbt's `path:` selector. |
| Path with `+` | `+path:models/marts` | Path match plus upstream/downstream expansion. |

When a SQLBuild model is selected, its immediate dbt upstream dependencies are always included so dbt can build the tables that SQLBuild models read from.

### dbt-only selectors

Selectors that SQLBuild does not recognize (like `state:modified`, `package:stripe`, `source:stripe.charges`) are passed to `dbt ls` to resolve:

| Selector | Example | Behavior |
|----------|---------|----------|
| Without `+` | `state:modified` | dbt-only work. No SQLBuild models selected. |
| With trailing `+` | `state:modified+` | SQLBuild runs `dbt ls` to find which dbt models match, then walks downstream into SQLBuild territory. |
| With both `+` | `+state:modified+` | Same downstream expansion, plus upstream dbt expansion. |

This means you can use dbt-native selectors like `state:modified+` to trigger rebuilds of SQLBuild models that depend on changed dbt models. If `dbt ls` returns no matching models, no SQLBuild work is triggered.

### Exclude

`--exclude` removes matching SQLBuild models from the final selection:

```bash
sqb dbt build --select fact_orders+ --exclude tag:nightly
```

### Examples

```bash
# Build a specific SQLBuild model and its dbt dependencies
sqb dbt build --select downstream_orders

# Build everything downstream of a SQLBuild model
sqb dbt build --select downstream_orders+

# Build a SQLBuild model with full upstream dbt chain
sqb dbt build --select +downstream_orders

# Build SQLBuild models downstream of modified dbt models
sqb dbt build --select state:modified+

# Build all SQLBuild models tagged "nightly" with their dbt dependencies
sqb dbt build --select tag:nightly

# Build SQLBuild models under a path
sqb dbt build --select path:models/marts
```

### Execution order

For `sqb dbt run` and `sqb dbt build`:

1. **dbt runs** - a single `dbt run/build` command executes with the user's selectors merged with any additional dbt models required by selected SQLBuild models
2. **SQLBuild runs** - selected SQLBuild models execute against the now-built dbt tables

## Adding SQLBuild models

Source: `concepts/dbt-compatibility/adding-sqlbuild-models.mdx`

Grow into SQLBuild's own models, tests, audits, and scenarios downstream of your dbt project.

The dbt compatibility bridge does not require SQLBuild models. You can optionally add SQLBuild models, tests, audits, and scenarios downstream of dbt outputs.

This is purely additive. Your dbt models stay in dbt, and the layout gains a `models/` directory in the SQLBuild project.

```
my-workspace/
  analytics/                  # your existing dbt project, untouched
    dbt_project.yml
    models/
    target/
      manifest.json
  sqlbuild_project/           # created by SQLBuild
    sqlbuild_project.toml
    models/
      marts/downstream_orders.sql   # references dbt models via __dbt_ref
    tests/
      unit/test_downstream_orders.sql
```

### Referencing dbt models

SQLBuild models reference dbt model outputs with `__dbt_ref("package", "model")`:

```sql
MODEL (
  tags [finance],
  columns (order_id (audits [not_null])),
);

SELECT order_id FROM __dbt_ref("analytics", "fact_orders")
```

This resolves to the qualified warehouse table name from the dbt manifest (e.g. `analytics.fact_orders`). The dbt model becomes an upstream dependency in the combined graph, so SQLBuild models downstream of it build against its output.

SQLBuild models can also reference other SQLBuild models with `__ref()` as usual:

```sql
MODEL (tags [marts]);

SELECT order_id FROM __ref("downstream_orders")
```

### Tests, audits, and scenarios

SQLBuild models added downstream of dbt get SQLBuild's full validation surface:

- **Unit tests** can mock dbt model dependencies with `__dbt_ref__` fixture CTEs, so you can test a SQLBuild model without a warehouse connection or a compiled dbt manifest. See [Testing](/concepts/testing).
- **Audits** declared inline in the `MODEL()` header block promotion when they fail, the same as in a standalone SQLBuild project. See [Audits](/concepts/audits).
- **Scenarios** run the combined graph against fixture inputs for end-to-end checks. See [Scenarios](/concepts/scenarios).

For the full model authoring reference (materializations, incremental strategies, contracts, and more), see [Models](/concepts/models).

## Project Configuration

Source: `concepts/project-configuration.mdx`

Configure your SQLBuild project with sqlbuild_project.toml and sqlbuild_local.toml.

SQLBuild projects are configured with two files in the project root:

- **`sqlbuild_project.toml`** - shared project configuration, committed to version control
- **`sqlbuild_local.toml`** - local developer overrides, gitignored

Macro, constant, and enum visibility is not configured in either file. Declaration scopes use filesystem conventions; see [Declaration Scopes](/concepts/declaration-scopes).

Most projects need only one committed `sqlbuild_project.toml`. Define shared targets such
as `dev` and `prod` there, including clone policies and team-wide defaults. Do not maintain
separate complete project files for each environment.

Create `sqlbuild_local.toml` only when a developer or execution environment needs different
target selection, credentials, schemas, adapter settings, or variables. SQLBuild loads it
automatically and merges its explicitly configured values over the shared project config.

```text
project/
  sqlbuild_project.toml   # committed: shared targets and behavior
  sqlbuild_local.toml     # gitignored: this developer's overrides
```

Add the local file to `.gitignore`:

```gitignore
sqlbuild_local.toml
```

### sqlbuild_project.toml

A complete example:

```toml
name = "waffle_shop"
adapter = "duckdb"
default_target = "dev"

[connections.local]
database = "waffle_shop_control.duckdb"

[settings]
default_audit_severity = "warn"

[defaults]
materialized = "table"

[constants]
collection_rendering = "value_list"

[targets.prod]
connection = "local"
schema = "prod"

[targets.dev]
connection = "local"
schema = "dev"

[path_defaults."models/staging"]
materialized = "view"
```

#### Required fields

| Field | Description |
|-------|-------------|
| `name` | Project name. Used in fingerprint tracking and manifest generation. |
| `adapter` | Database adapter: `duckdb`, `motherduck`, `snowflake`, `bigquery`, `databricks`, `postgres`, or `sqlserver`. See [Adapters](/concepts/adapters). |
| `default_target` | Name of the target to build against when none is selected (see [Targets](#targets)). |

#### Named connections

Define reusable connections under `[connections.<name>]`, then reference one by name from
each target. Connections own endpoint, authentication, and compute settings. Targets own the
authoritative `database`, `schema`, variables, and operational policy.

```toml
[connections.local]
database = "my_project.duckdb"

[targets.dev]
connection = "local"
schema = "dev"
```

Multiple targets can reuse one connection while keeping separate namespaces and policies:

```toml
[connections.warehouse]
account = "my_org-my_account"
user = "${ENV:SNOWFLAKE_USER}"
password = "${ENV:SNOWFLAKE_PASSWORD}"
warehouse = "TRANSFORM_WH"

[targets.prod]
connection = "warehouse"
database = "ANALYTICS"
schema = "PROD"

[targets.dev]
connection = "warehouse"
database = "ANALYTICS"
schema = "DEV_ALICE"
```

A `database` or `schema` present in a named connection is connection/session metadata only;
it does not satisfy the mandatory namespace strategy for a named target. Put the target's
authoritative database and schema on `[targets.<name>]`. SQLBuild validates connection
references while loading configuration, without opening a warehouse connection, and reports
an unknown `targets.<name>.connection` name as an offline configuration error.

For migration only, SQLBuild still maps legacy `[connection]` to an implicit connection and
legacy `[targets.<name>.connection]` blocks to target-specific implicit connections. These
forms are compatibility syntax, not the canonical format for new or updated projects.

### Targets

A target is a named build context - the database and schema you build into, plus execution policy (for example `dev` and `prod`). Each target references a named connection and can configure:

| Field | Description |
|-------|-------------|
| `schema` | Schema for all models in this target; required for named targets |
| `loader_schema` | Default write schema for managed source loaders; falls back to `schema` |
| `database` | Database for all models in this target |
| `connection` | Name from `[connections.<name>]` used for endpoint, authentication, and compute |
| `vars` | Target-specific project variables |
| `defer_sources_to` | Target name to read managed source data from (see [Loaders](/concepts/python-nodes/loaders#source-deferral)) |
| `clone` | Clone policy (see below) |

```toml
[connections.warehouse]
account = "my_org-my_account"
warehouse = "TRANSFORM_WH"

[targets.prod]
connection = "warehouse"
database = "analytics"
schema = "analytics_prod"
loader_schema = "raw_prod"
defer_sources_to = "prod"

[targets.dev]
connection = "warehouse"
database = "analytics"
schema = "analytics_dev"
loader_schema = "raw_dev"
defer_sources_to = "prod"

[targets.staging]
connection = "warehouse"
database = "analytics"
schema = "staging"

```

Managed loader writes use the active target's `loader_schema`, falling back to its model
`schema`. Managed source reads use the target named by `defer_sources_to`, or the active
target itself when deferral is omitted. In the example, `load --target dev` writes to
`raw_dev`, while models built in dev read from `raw_prod`.

SQLBuild rejects targets on the same warehouse/database when their managed loader writes
resolve to the same schema. Two targets may read the same schema through deferral, but they
cannot both own loader writes there.

#### Selecting a target

The active target is determined by (in order of precedence):

1. `--target` on the command line (highest priority)
2. `sqlbuild_local.toml` `target` field
3. `default_target` in `sqlbuild_project.toml`
4. No target (models build to the default schema)

A typical developer keeps shared target definitions in `sqlbuild_project.toml` and selects
their normal target once in the optional local file:

```toml
# sqlbuild_local.toml
target = "dev"

[targets.dev]
connection = "warehouse"
schema = "dev_alice"
loader_schema = "raw_alice"

[connections.warehouse]
user = "alice"
password = "${ENV:SNOWFLAKE_PASSWORD}"
```

Commands then use `dev` automatically. An explicit command such as `sqb build --target prod`
still takes precedence for that invocation.

#### Clone policies

Targets can declare whether they allow cloning to or from:

```toml
[targets.prod]
schema = "prod"

[targets.prod.clone]
allow_as_clone_origin = true
allow_as_clone_destination = false

[targets.dev]
schema = "dev"

[targets.dev.clone]
allow_as_clone_origin = false
allow_as_clone_destination = true
```

Both policies default to `false`. `sqb clone --from prod --to dev` requires `allow_as_clone_origin = true` on `prod` and `allow_as_clone_destination = true` on `dev`.

### Defaults

Project-wide model defaults. Any field you can set in a `MODEL()` header can be set here as a default:

```toml
[defaults]
materialized = "table"
incremental_strategy = "delete_insert"
replay_on_change = "full"
tags = ["managed"]
```

These apply to all models unless overridden by path defaults or the model's own `MODEL()` header.

### Constants

Collection constants default to parenthesized SQL value lists. Set a project-wide default when lists and sets should instead compile to first-class adapter-native arrays:

```toml
[constants]
collection_rendering = "array"
```

`collection_rendering` accepts `value_list` (the SQLBuild default) or `array`. A public constant's `render_as` field or a model-local `constant(...)` wrapper overrides the project setting. The complete precedence order is declaration override, project setting, then `value_list`.

This setting does not make unsupported adapter features portable. In particular, SQL Server rejects native arrays, and BigQuery rejects nested arrays. See [Collections and Rendering](/concepts/constants/collections-and-rendering#project-default) for syntax, adapter output, and value-list usage constraints.

### Path defaults

Per-directory model defaults. Useful for applying different config to different parts of your project:

```toml
[path_defaults."models/staging"]
materialized = "view"
tags = ["staging"]

[path_defaults."models/marts"]
materialized = "table"
tags = ["marts"]
replay_on_change = "full"
```

Path matching uses the model's relative file path. A model at `models/staging/stg_orders.sql` matches the `models/staging` path default.

#### Config layering order

Configuration is layered in this order, with later layers overriding earlier ones:

1. **Project defaults** (`defaults`)
2. **Path defaults** (`path_defaults`) - if the model's path matches
3. **MODEL() header** - the model's own config

Most keys are overridden by the more specific layer, but three merge instead:

- `tags` are *unioned* across layers. A model with `tags [marts]` in its header that matches a path default with `tags [managed]` will have both tags.
- `row_diff_exclude_columns` lists are unioned across layers.
- `row_diff_tolerances` mappings are deep-merged across layers, so a header tolerance for one column adds to (rather than replaces) tolerances declared in defaults or path defaults.

### Settings

Global feature toggles:

```toml
[settings]
sql_analysis = true
query_change_tracking = true
sql_validation = true
column_contract_mode = "implicit"
concurrency = 1
auto_load_sources = true
table_promotion_mode = "staged"
default_audit_severity = "warn"
default_audit_run_scope = "final"
```

| Field | Default | Description |
|-------|---------|-------------|
| `sql_analysis` | `true` | Enable SQL validation and static analysis at compile time |
| `changes_only` | `false` | Enable [change-aware pruning](/concepts/planning#changes-only-mode) for `plan` and `build` without passing `--changes-only` each run. Requires `virtual_environments = true`; rejected in direct mode. Can also be set per target under `[targets.<name>]`. The CLI flag takes precedence, then the selected target, then local settings, then this project setting. |
| `virtual_environments` | `false` | Enable [virtual environments](/concepts/virtual-environments) (versioned model outputs, promotion, rollback, state management). When `false`, the project runs in direct mode. |
| `query_change_tracking` | `true` | Track query fingerprints for change detection |
| `sql_validation` | `true` | Validate SQL syntax during compilation |
| `column_contract_mode` | `implicit` | Controls whether column declarations on models without a `contract` declaration activate static shape/nullability validation. `implicit` preserves that validation; `explicit` treats columns as metadata and audit attachment unless the model declares `contract enforced`. Model-level `contract enforced` and `contract none` override this setting. Explicit type enforcement remains independent. See [Contracts](/concepts/models/contracts). |
| `concurrency` | `1` | Maximum parallel model execution (currently serial only) |
| `auto_load_sources` | `true` | Automatically run source loaders before building dependent models during `sqb build`. See [Loaders](/concepts/python-nodes/loaders). |
| `table_promotion_mode` | adapter default | `staged` (CTAS to staging, audit, then promote) or `immediate` (CTAS directly to target, then audit) |
| `default_audit_severity` | `warn` | Default severity for audits: `warn` or `error` |
| `default_audit_run_scope` | `final` | Default run scope for audits: `final` or `delta_and_final` |

#### Table promotion mode

- **`staged`** (default for most adapters): Materializes into a staging table, runs audits, then swaps into the target. If audits fail, the production table is untouched.
- **`immediate`**: Creates the table directly at the target location. Audits run after materialization. Simpler but no pre-promotion safety net.

### Kata

Kata policy belongs in the shared `sqlbuild_project.toml` so local and CI evaluation use the same
architecture rules:

```toml
[kata]
select = ["SQBK"]
```

Kata is opt-in. `SQBK` activates every built-in rule; narrower prefixes activate a rule family, and
exact codes activate individual rules. Audit, SQL test, and custom-rule test-case minimums each
default to one and can be overridden under `[kata.thresholds]`. See
[Kata SQL Architecture Checks](/concepts/kata) for the complete rule, configuration, and suppression
reference.

### Project variables

Variables are simple string substitutions available in model SQL via the `@@name` syntax:

```toml
[vars]
schema_prefix = "analytics"
retention_days = "90"
```

Target-specific variables override project-level ones:

```toml
[vars]
schema_prefix = "analytics"

[targets.prod.vars]
schema_prefix = "prod_analytics"
```

See [Macros](/concepts/macros) for details on variable substitution and how variables interact with macros.

### Janitor

Configuration for the `sqb janitor` command, which cleans up stale warehouse relations:

```toml
[janitor]
enabled = false
retention_days = 30
delete_tracked_only = true
exclude_patterns = ["audit_*", "tmp_*"]
```

| Field | Default | Description |
|-------|---------|-------------|
| `enabled` | `false` | Whether janitor is active |
| `retention_days` | `30` | Only clean relations older than this many days |
| `delete_tracked_only` | `true` | Only clean relations that appear in fingerprint tracking |
| `exclude_patterns` | `[]` | Glob patterns for relations to skip |

### Scenario

Configuration for scenario snapshot capture safety limits and local type overrides:

```toml
[scenario.snapshot_limits]
max_rows_per_relation = 10000
max_total_rows = 50000
max_bytes_per_relation = 10485760
max_total_bytes = 52428800
```

| Field | Default | Description |
|-------|---------|-------------|
| `max_rows_per_relation` | none | Maximum rows per captured relation |
| `max_total_rows` | none | Maximum total rows across all relations in one scenario |
| `max_bytes_per_relation` | none | Maximum JSONL bytes per relation file |
| `max_total_bytes` | none | Maximum total JSONL bytes per scenario |

Local type overrides for DuckDB replay are configured per adapter dialect:

```toml
[scenario.local_type_overrides.snowflake]
"OBJECT" = "JSON"
"ARRAY" = "JSON"
```

See [Scenarios](/concepts/scenarios) for details on local type overrides and capture limits.

### dbt

Configuration for running SQLBuild alongside an existing dbt project:

```toml
[dbt]
project_dir = "../dbt_project"
profiles_dir = "../profiles"
target_path = "../dbt_project/target"
target = "dev"
```

| Field | Description |
|-------|-------------|
| `project_dir` | Path to the dbt project root (where `dbt_project.yml` lives) |
| `profiles_dir` | Path to the directory containing `profiles.yml` |
| `target_path` | Path to dbt's `target/` directory (where `manifest.json` is written) |
| `target` | dbt target name override (optional) |

Paths can be absolute or relative to the SQLBuild project root. See [Using SQLBuild with dbt](/concepts/dbt-compatibility/overview) for setup and usage details.

### Skills

Configuration for AI agent skill file installation:

```toml
[skills]
targets = ["agents", "claude"]
auto_update = false
```

| Field | Default | Description |
|-------|---------|-------------|
| `targets` | `["agents", "claude"]` | Agent targets to install. OpenCode consumes `.agents`; use `opencode` only as an explicit override. |
| `auto_update` | `false` | Refresh stale SQLBuild-owned generated files from the installed package during normal commands; custom collisions are never overwritten. |

See [skills CLI reference](/cli/skills) for usage details.

### sqlbuild_local.toml

Local developer overrides. This optional file is loaded automatically and should be
gitignored. Only put values that differ from the shared project configuration here.

```toml
target = "dev"

[targets.dev]
schema = "dev_alice"
loader_schema = "raw_alice"

[connections.local]
database = "my_local.duckdb"

[settings]
sql_validation = false
concurrency = 4

[vars]
debug_mode = "true"
```

| Field | Description |
|-------|-------------|
| `target` | Override which target is active for this developer |
| `adapter` | Override the database adapter (e.g. use DuckDB locally while prod uses Snowflake) |
| `connections` | Override named connection fields; entries merge by connection name |
| `settings` | Override global settings (only explicitly set fields take effect) |
| `vars` | Developer-specific variable overrides (merged on top of project + target vars) |

Project and local configuration merge named connections by name and merge their explicitly
configured fields. Target blocks merge the same way and may override the connection reference,
`database`, `schema`, `loader_schema`, variables, source deferral, and policy fields. Unspecified
values continue to come from `sqlbuild_project.toml`; a local reference to an unknown merged
connection still fails offline during configuration loading.

This replaces the common dbt pattern of switching profiles or setting environment variables
to change targets. Each developer sets their target, named connection, and preferences once in
`sqlbuild_local.toml` and it persists across sessions.

## Resource Identities

Source: `concepts/resource-identities.mdx`

Canonical names for SQLBuild resources, selectors, state, and integrations.

SQLBuild resource identities use lowercase ASCII snake_case. A name must start with a lowercase
letter, end with a lowercase letter or digit, and contain only lowercase letters, digits, and
underscores. Consecutive underscores are valid, so established names such as
`race__mart_v_entry` remain canonical.

This contract applies to models, seeds, sources, SQL and Python functions, generic and singular
audits, attached audit definitions and instance names, SQL tests and parameterized cases,
scenarios, SQL and Python hooks, macros, model schemas, enums, constants, materializations,
providers, event exporters, loaders, tasks, assets, and checks. Private scoped declarations use
exactly one leading underscore, such as `_country_codes`; public declarations must not use a
leading underscore.

Provider classes are the one conventional derivation: when `provider_name` is omitted,
`AnalyticsApiProvider` resolves to `analytics_api_provider`. An explicit `provider_name` is an
authored identity and must already be canonical snake_case; SQLBuild does not normalize it.

Names derived from files use the filename stem. For example, `models/daily_orders.sql` defines
the model identity `daily_orders`, while `audits/generic/expression_is_true.sql` defines the
generic audit identity `expression_is_true`. Directories organize resources but do not change
their names.

Physical warehouse identifiers are separate from SQLBuild resource identities. Database, schema,
table, model alias, column, tag, group, and directory names retain their existing adapter-specific
contracts and do not need to follow this profile.

### Invalid names

Compilation fails during discovery with `D016` when an authored identity is not canonical:

```text
error[D016]: Invalid model identity 'DailyOrders' in models/DailyOrders.sql;
use snake_case 'daily_orders'
```

SQLBuild suggests a corrected spelling but never silently normalizes an identity. Silent
normalization would make selectors, manifests, persisted execution state, and integration keys
disagree about which resource ran.

### Migrating existing projects

1. Rename file-derived resources and explicit `name` values to snake_case.
2. Update `__ref`, `__seed`, `__source`, function, hook, macro, audit, test, and dependency
   references.
3. Update selectors and external integrations, including Dagster asset/check keys, that use the
   old identity.
4. Compile before building.

A rename intentionally creates a new resource identity. Existing fingerprints, audit history,
and other persisted state under the old name are not silently reassigned to the new resource.

## Overview

Source: `concepts/adapters.mdx`

Supported database engines and their connection configuration.

SQLBuild uses adapters to connect to different database engines.

| Adapter | Status | Install |
|---------|--------|---------|
| [DuckDB](/concepts/adapters/duckdb) | Supported | included by default |
| [MotherDuck](/concepts/adapters/motherduck) | Supported | included by default (uses DuckDB) |
| [Snowflake](/concepts/adapters/snowflake) | Supported | `sqlbuild[snowflake]` |
| [BigQuery](/concepts/adapters/bigquery) | Supported | `sqlbuild[bigquery]` |
| [Databricks](/concepts/adapters/databricks) | Supported | `sqlbuild[databricks]` |
| [PostgreSQL](/concepts/adapters/postgres) | Supported | `sqlbuild[postgres]` |
| [SQL Server](/concepts/adapters/sqlserver) | Supported | `sqlbuild[sqlserver]` |
| ClickHouse | Coming soon | |
| Redshift | Coming soon | |
| Trino | Coming soon | |
| Spark | Coming soon | |
| Athena | Coming soon | |

Set the adapter in `sqlbuild_project.toml`:

```toml
name = "my_project"
adapter = "duckdb"
```

Or override it per developer in `sqlbuild_local.toml`:

```toml
adapter = "duckdb"
```

### Custom adapters

You can write your own adapter for any database engine by placing Python files under `adapters/` in your project directory.

#### Extending a built-in adapter

The most common case is extending an existing adapter with custom behavior. Subclass the built-in adapter, set a new `adapter_name`, and override what you need:

```python
# adapters/duckdb_plus.py
from sqlbuild.integrations.duckdb.client import DuckDbAdapter

class DuckDbPlusAdapter(DuckDbAdapter):
    adapter_name = "duckdb_plus"

    def connect(self, config):
        connection = super().connect(config)
        # custom setup - load extensions, set pragmas, etc.
        self.execute(connection, "SET enable_progress_bar = true")
        return connection
```

```toml
adapter = "duckdb_plus"
```

#### Writing an adapter from scratch

For a database engine with no built-in support, subclass `BaseAdapter`. It provides ANSI SQL defaults for most methods - you only need to implement `connect`, `execute`, `close`, and any methods where your engine differs from standard SQL:

```python
# adapters/my_database.py
from sqlbuild.adapter.base.base_adapter import BaseAdapter

class MyDatabaseAdapter(BaseAdapter):
    adapter_name = "my_database"
    sql_analysis_dialect_name = "postgres"  # SQL dialect for validation and lineage

    def connect(self, config):
        ...

    def execute(self, connection, sql):
        ...

    def close(self, connection):
        ...
```

Set `sql_analysis_dialect_name` to the SQL dialect name that matches your engine's SQL syntax. This enables compile-time SQL validation, column inference, column lineage, and local scenario replay for your adapter. If omitted, SQLBuild uses generic SQL parsing. SQL analysis is powered by [Polyglot](https://github.com/tobilg/polyglot), a Rust reimplementation of SQLGlot supporting 32+ dialects.

For full control with no inherited defaults, subclass `StrictAdapter` instead. Every method is abstract and must be implemented explicitly. SQLBuild raises a clear error listing any unimplemented methods.

#### Discovery rules

- SQLBuild discovers all `.py` files under `adapters/` recursively (excluding `__init__.py` and files starting with `_`)
- Each file is scanned for classes that define a string `adapter_name` and subclass `StrictAdapter` (or any of its subclasses like `BaseAdapter` or a built-in adapter)
- Adapter names must be unique across all adapter files - duplicates raise an error
- Custom adapter names cannot shadow built-in names (`duckdb`, `snowflake`, `bigquery`, `databricks`, `postgres`, `sqlserver`)

#### Adapter class hierarchy

```
StrictAdapter          (fully abstract - all methods must be implemented)
  └── BaseAdapter      (ANSI SQL defaults - override only what differs)
        ├── DuckDbAdapter
        ├── SnowflakeAdapter
        ├── BigQueryAdapter
        ├── DatabricksAdapter
        ├── PostgresAdapter
        └── SqlServerAdapter
```

`StrictAdapter` composes four mixins that define the full adapter contract:

- **ConnectionMixin** - `connect`, `close`, `begin`, `commit`, `rollback`
- **SchemaMixin** - `relation_exists`, `list_relations`, `describe_relation`, `ensure_schema`
- **MaterializationMixin** - `create_table_as`, `create_view`, `drop`, `rename`, `swap`, `load_seed`
- **DiffMixin** - `diff_schema`, `diff_rows`, `sample_unequal_rows`, `sample_side_only_rows`

## DuckDB

Source: `concepts/adapters/duckdb.mdx`

DuckDB adapter configuration for SQLBuild.

DuckDB is included as a core dependency. No extra installation needed.

### Connection config

```toml
adapter = "duckdb"
default_target = "dev"

[connections.local]
database = "my_project.duckdb"

[targets.dev]
connection = "local"
schema = "dev"
```

| Field | Description |
|-------|-------------|
| `database` | Path to the DuckDB database file. Use `:memory:` for in-memory databases. |
| `extensions` | List of DuckDB extensions to install and load on connect. |
| `settings` | Key-value pairs passed as `SET` statements on connect. |
| `attach` | List of additional databases to attach. |

### Extensions and settings

```toml
[connections.local]
database = "my_project.duckdb"
extensions = ["httpfs", "parquet"]

[connections.local.settings]
memory_limit = "4GB"
```

### Attaching additional databases

```toml
[connections.local]
database = "my_project.duckdb"

[[connections.local.attach]]
path = "external_data.duckdb"
alias = "external"
read_only = true
```

### Table promotion mode

DuckDB defaults to `staged` promotion: tables are materialized into a staging table, audited, then swapped into the target. This is configurable in `settings`:

```toml
[settings]
table_promotion_mode = "staged"
```

## MotherDuck

Source: `concepts/adapters/motherduck.mdx`

MotherDuck adapter configuration for SQLBuild.

MotherDuck uses DuckDB's built-in `md:` connection support. No extra installation needed beyond the core DuckDB dependency.

### Connection config

```toml
adapter = "motherduck"
default_target = "dev"

[connections.motherduck]
database = "my_database"
token = "your_motherduck_token"

[targets.dev]
connection = "motherduck"
database = "my_database"
schema = "dev"
```

| Field | Description |
|-------|-------------|
| `database` | MotherDuck database name. Automatically prefixed with `md:` if not already present. Defaults to `md:` (your default MotherDuck database). |
| `token` | MotherDuck access token. Can also be set via environment variable. |

### Authentication

MotherDuck requires an access token. Generate one from the MotherDuck UI and pass it via the connection config or an environment variable:

```toml
[connections.motherduck]
database = "my_database"
token = "${ENV:MOTHERDUCK_TOKEN}"
```

### Shared connections across targets

Use targets to separate production and development databases on MotherDuck:

```toml
adapter = "motherduck"

[connections.motherduck]
token = "${ENV:MOTHERDUCK_TOKEN}"
database = "my_database"

[targets.prod]
connection = "motherduck"
database = "prod_db"
schema = "prod"

[targets.dev]
connection = "motherduck"
database = "dev_db"
schema = "dev"
```

### Local development with DuckDB

Use `sqlbuild_local.toml` to override the adapter for local development against a plain DuckDB file:

```toml
adapter = "duckdb"

[connections.local]
database = "local_dev.duckdb"

[targets.dev]
connection = "local"
schema = "dev"
```

This lets you develop and test locally with zero MotherDuck compute cost, then deploy to MotherDuck in production. SQLBuild's [scenario replay](/concepts/scenarios) also runs locally in DuckDB regardless of the production adapter.

## Snowflake

Source: `concepts/adapters/snowflake.mdx`

Snowflake adapter configuration for SQLBuild.

Snowflake requires the optional `snowflake-connector-python` dependency:

```bash
pip install 'sqlbuild[snowflake]'
# or
uv pip install 'sqlbuild[snowflake]'
```

### Connection config

```toml
adapter = "snowflake"
default_target = "dev"

[connections.warehouse]
account = "my_org-my_account"
user = "my_user"
password = "my_password"
role = "TRANSFORM_ROLE"
warehouse = "TRANSFORM_WH"

[targets.dev]
connection = "warehouse"
database = "ANALYTICS"
schema = "RAW"
```

Connection fields are passed directly to `snowflake.connector.connect()`. See the [Snowflake Connector documentation](https://docs.snowflake.com/en/developer-guide/python-connector/python-connector-connect) for all available options, including key-pair authentication, OAuth, and SSO. Put the authoritative database and schema on the target.

### Session initialization

On connect, SQLBuild applies the connection's role and warehouse, then applies the active
target's authoritative database and schema. These ensure the session context is set correctly
regardless of the user's default settings.

### Shared connections across targets

Use multiple targets to reuse one Snowflake connection while selecting different authoritative
databases and schemas:

```toml
adapter = "snowflake"

[connections.warehouse]
account = "my_org-my_account"
user = "my_user"
password = "my_password"
role = "TRANSFORM_ROLE"
warehouse = "TRANSFORM_WH"

[targets.prod]
connection = "warehouse"
database = "PROD_DB"
schema = "prod"

[targets.dev]
connection = "warehouse"
database = "DEV_DB"
schema = "dev"
```

## BigQuery

Source: `concepts/adapters/bigquery.mdx`

BigQuery adapter configuration for SQLBuild.

BigQuery requires the optional `google-cloud-bigquery` dependency:

```bash
pip install 'sqlbuild[bigquery]'
# or
uv pip install 'sqlbuild[bigquery]'
```

### Connection config

```toml
adapter = "bigquery"
default_target = "dev"

[connections.gcp]
project = "my-gcp-project"
location = "europe-west2"

[targets.dev]
connection = "gcp"
database = "my-gcp-project"
schema = "analytics_dev"
```

| Field | Description |
|-------|-------------|
| `project` | GCP project ID (required) |
| `location` | BigQuery dataset location - a region (`europe-west2`, `us-east1`) or multi-region (`US`, `EU`) |
| `credentials_path` | Path to a service account JSON key file. If omitted, uses Application Default Credentials (ADC). |

### Authentication

BigQuery supports two authentication methods:

**Application Default Credentials (default):** Uses the credentials from `gcloud auth application-default login` or the environment's service account. No config needed beyond `project`.

**Service account file:**

```toml
[connections.gcp]
project = "my-gcp-project"
credentials_path = "/path/to/service-account.json"
```

### Typed constants

BigQuery renders typed constant arrays with bracket syntax, objects as native JSON expressions, and exact decimals as `NUMERIC` expressions. For example:

```sql
['GB', 'FR', 'HK']
JSON '{"GB":"Great Britain"}'
NUMERIC '2.4700'
```

BigQuery does not support arrays of arrays. A nested list or set requested with `render_as array` fails at compile time rather than producing invalid BigQuery SQL. Parenthesized `value_list` rendering remains available for ordinary scalar collections used with `IN`.

See [Collections and Rendering](/concepts/constants/collections-and-rendering#native-array-rendering) for declarations, rendering precedence, and the cross-adapter matrix.

## Databricks

Source: `concepts/adapters/databricks.mdx`

Databricks adapter configuration for SQLBuild.

Databricks requires the optional `databricks-sql-connector` dependency:

```bash
pip install 'sqlbuild[databricks]'
# or
uv pip install 'sqlbuild[databricks]'
```

### Connection config

```toml
adapter = "databricks"
default_target = "dev"

[connections.workspace]
server_hostname = "my-workspace.cloud.databricks.com"
http_path = "/sql/1.0/warehouses/abc123"
token = "dapi_my_access_token"

[targets.dev]
connection = "workspace"
database = "my_catalog"
schema = "my_schema"
```

| Field | Description |
|-------|-------------|
| `server_hostname` | Databricks workspace hostname (required) |
| `http_path` | SQL warehouse or cluster HTTP path (required) |
| `token` | Personal access token (required) |

The target's `database` selects the Unity Catalog catalog, and its `schema` selects the schema.

### Session initialization

On connect, SQLBuild runs `USE CATALOG` and `USE SCHEMA` statements from the active target to set
the authoritative session namespace.

## PostgreSQL

Source: `concepts/adapters/postgres.mdx`

PostgreSQL adapter configuration for SQLBuild.

PostgreSQL requires the optional `psycopg` dependency:

```bash
pip install 'sqlbuild[postgres]'
# or
uv pip install 'sqlbuild[postgres]'
```

### Connection config

```toml
adapter = "postgres"
default_target = "dev"

[connections.postgres]
host = "localhost"
port = 5432
user = "my_user"
password = "my_password"
dbname = "my_database"

[targets.dev]
connection = "postgres"
database = "my_database"
schema = "analytics_dev"
```

| Field | Description |
|-------|-------------|
| `host` | PostgreSQL server hostname (default: `localhost`) |
| `port` | PostgreSQL server port (default: `5432`) |
| `user` | Database user |
| `password` | Database password |
| `dbname` | Database name |

Connection fields are passed to `psycopg.connect()`. See the [psycopg documentation](https://www.psycopg.org/psycopg3/docs/api/connections.html) for all available options. The target remains authoritative for database and schema qualification.

### Shared connections across targets

```toml
adapter = "postgres"

[connections.postgres]
host = "localhost"
user = "my_user"
password = "${ENV:PG_PASSWORD}"
dbname = "analytics"

[targets.prod]
connection = "postgres"
database = "analytics"
schema = "prod"

[targets.dev]
connection = "postgres"
database = "analytics"
schema = "dev"
```

## SQL Server

Source: `concepts/adapters/sqlserver.mdx`

Microsoft SQL Server adapter configuration for SQLBuild.

SQL Server requires the optional `pymssql` dependency:

```bash
pip install 'sqlbuild[sqlserver]'
# or
uv pip install 'sqlbuild[sqlserver]'
```

### Connection config

```toml
adapter = "sqlserver"
default_target = "dev"

[connections.sqlserver]
host = "localhost"
port = 1433
user = "sa"
password = "my_password"
database = "my_database"

[targets.dev]
connection = "sqlserver"
database = "my_database"
schema = "analytics_dev"
```

| Field | Description |
|-------|-------------|
| `host` | SQL Server hostname (default: `localhost`). Also accepts `server` as an alias. |
| `port` | SQL Server port (default: `1433`) |
| `user` | Database user (default: `sa`). Also accepts `username` as an alias. |
| `password` | Database password |
| `database` | Database name (default: `master`). Also accepts `dbname` as an alias. |

Connection fields are passed to `pymssql.connect()`. See the [pymssql documentation](https://pymssql.readthedocs.io/en/stable/ref/pymssql.html) for all available options. The target remains authoritative for database and schema qualification.

SQL Server supports schema-only, full-row, and bounded `sqb diff` comparisons.

### Typed constants

SQL Server supports scalar and parenthesized `value_list` constants. Strings use Unicode literals where required, and objects render through a JSON expression such as:

```sql
JSON_QUERY(N'{"GB":"Great Britain"}')
```

SQL Server has no supported first-class native array expression. Any list or set that resolves to `render_as array`, whether through its declaration or `[constants].collection_rendering`, fails at compile time. SQLBuild does not silently substitute a value list or quoted JSON string.

See [Collections and Rendering](/concepts/constants/collections-and-rendering#native-array-rendering) for declarations, rendering precedence, and the cross-adapter matrix.

### Shared connections across targets

```toml
adapter = "sqlserver"

[connections.sqlserver]
host = "localhost"
user = "sa"
password = "${ENV:MSSQL_PASSWORD}"
database = "analytics"

[targets.prod]
connection = "sqlserver"
database = "analytics"
schema = "prod"

[targets.dev]
connection = "sqlserver"
database = "analytics"
schema = "dev"
```

## Sources

Source: `concepts/sources.mdx`

Declare external data inputs for your pipeline.

Sources declare external data that your models depend on. They are defined in YAML files under `sources/` in your project directory.

### Table sources

Point at an existing table or view in your warehouse:

```yaml
sources:
  - name: raw_events
    database: analytics
    schema: raw
    table: events
```

Reference it in models with `__source("raw_events")`.

### Expression sources

Define source data inline as a SQL expression. No external tables or setup scripts needed:

```yaml
sources:
  - name: raw__customers
    expression: |
      SELECT * FROM (VALUES
        (1, 'Leslie', 'Knope', 'leslie@pawnee.gov', TIMESTAMP '2026-01-15 09:00:00'),
        (2, 'Ron', 'Swanson', 'ron@pawnee.gov', TIMESTAMP '2026-02-01 08:00:00')
      ) AS raw__customers(id, first_name, last_name, email, created_at)
```

Expression sources are resolved at compile time. They're the escape hatch for anything the framework doesn't natively model: external tables, warehouse-specific syntax, function calls, or any other relation type that doesn't fit a standard table reference.

An inline source expression uses macros, constants, and enums available from its source definition
under `sources/`. Declarations limited to one source folder are not available in sibling folders.
See [How Visibility Works](/concepts/declaration-scopes/visibility).

### Source audits

Sources support the same audit system as models. Audits attached to sources run before any dependent model is built:

```yaml
sources:
  - name: raw_orders
    columns:
      - name: id
        audits:
          - not_null
          - unique
    audits:
      - expression_is_true:
          name: no future orders
          expression: "ordered_at <= CURRENT_TIMESTAMP"
```

If a source audit with `error` severity fails, all downstream models that depend on that source are blocked.

### Type enforcement

Type enforcement is implicit for sources. If any column declares a `type`, SQLBuild activates source type enforcement, casts that column during source resolution, and uses declared types for schema-change detection:

```yaml
sources:
  - name: raw__customers
    expression: |
      SELECT 1 AS id, 'Leslie' AS first_name, 'Knope' AS last_name
    columns:
      - name: id
        type: INTEGER
      - name: first_name
      - name: last_name
```

In this example, only `id` has a type declared, so only `id` is cast. Columns without a `type` are passed through unchanged.

For expression sources, SQLBuild probes the expression's output columns and builds a projection that casts typed columns while preserving the rest. For table sources, it uses warehouse metadata to validate that declared column names exist and applies casts accordingly.

You can explicitly set `type_enforcement: false` on a source to disable casting even when column types are declared.

### Managed sources (loaders)

Sources can be loaded by Python functions instead of pointing at existing tables or inline expressions. Set `managed: true` to bind a source to the `@loader` function **of the same name**, and SQLBuild will call it to populate the source table:

```yaml
sources:
  - name: raw_customers
    managed: true
    write_strategy: table
    columns:
      - name: id
        type: INTEGER
      - name: name
        type: VARCHAR
```

Managed sources support incremental write strategies (`table`, `append`, `delete_insert`, `merge`), cursor-based loading, and concurrent execution.

See [Loaders](/concepts/python-nodes/loaders) for the full guide on writing loader functions, write strategies, the loader context API, and auto-load behavior during builds.

#### Declarative integrations (no Python)

For common ingestion you can declare the source entirely in YAML, with no `@loader` function. SQLBuild generates the loader for you and runs it during the build:

- [dlt](/integrations/dlt) - declare `dlt_sources` for `rest_api`, `sql_database`, and `filesystem` sources.
- [ingestr](/integrations/ingestr) - add an `ingestr` block to a source to pull from 50+ sources.

### Source freshness

Source freshness lets SQLBuild observe whether a source's data has changed between runs. This feeds into [planning and change detection](/concepts/planning): under `--changes-only` (in virtual environments), models downstream of unchanged sources are skipped.

Configure freshness per source with a `freshness:` block:

```yaml
sources:
  - name: raw_events
    schema: raw
    table: events
    freshness:
      strategy: column
      column: updated_at
      type: timestamp
      lag_tolerance: 15m
```

#### Strategies

| Strategy | Description | Required fields |
|----------|-------------|-----------------|
| `adapter` | Uses warehouse metadata (e.g. Snowflake `LAST_ALTERED`). No query against the source table. | None |
| `column` | Reads `MAX(column)` from the source table. | `column`, `type` |
| `sql` | Runs a custom query that returns a single scalar value. | `query`, `type` |

##### adapter

```yaml
freshness:
  strategy: adapter
```

Uses adapter-level table metadata. Supported on Snowflake, BigQuery, Databricks, PostgreSQL, DuckDB, and SQL Server. Does not support `type`, `column`, or `query`.

##### column

```yaml
freshness:
  strategy: column
  column: updated_at
  type: timestamp
```

Queries `MAX(column)` from the source table. The column must be a plain column name (no expressions; use `sql` strategy for those). Requires `type`.

##### sql

```yaml
freshness:
  strategy: sql
  query: "SELECT MAX(version_id) FROM raw.events"
  type: integer
```

Runs an arbitrary SQL query that returns a single scalar. Requires `type`. Does not support `column`.

#### Type

The `type` field declares the value kind for comparison:

| Type | Description |
|------|-------------|
| `timestamp` | Datetime value. Supports `lag_tolerance`. |
| `integer` | Integer value. Change detected by exact comparison. |
| `string` | String value. Change detected by exact comparison. |

#### Lag tolerance

`lag_tolerance` is optional and only valid with `type: timestamp`. It declares how much the observed timestamp can drift from the previous observation before being treated as a change:

```yaml
freshness:
  strategy: column
  column: updated_at
  type: timestamp
  lag_tolerance: 2h
```

Accepts positive durations: `15m` (minutes), `2h` (hours), `1d` (days). If the current observation is within the tolerance of the previous one, the source is treated as unchanged.

#### Auto-observation

Sources without an explicit `freshness:` block are auto-observed using the `adapter` strategy if:

- The source has a physical table (not an expression source)
- The source is not managed
- The adapter supports table freshness metadata

This means most unmanaged table sources get freshness tracking automatically on adapters that support it, with no configuration needed.

Use [`sqb freshness`](/cli/freshness) to observe source freshness on demand without triggering a build. See [Source freshness](/concepts/planning/source-freshness) for how freshness feeds into change-aware builds.

#### Freshness config reference

| Field | Description |
|-------|-------------|
| `strategy` | Observation strategy: `adapter`, `column`, or `sql` |
| `type` | Value kind: `timestamp`, `integer`, or `string` |
| `column` | Column name for `column` strategy |
| `query` | SQL query for `sql` strategy |
| `lag_tolerance` | Duration tolerance for timestamp comparisons (e.g. `15m`, `2h`, `1d`). Only valid with `type: timestamp`. |

### Config reference

| Field | Description |
|-------|-------------|
| `name` | Source name, used in `__source("name")` references |
| `database` | Target database (optional) |
| `schema` | Physical source schema (optional). For managed sources, overrides target `loader_schema`; otherwise managed loaders fall back to `loader_schema`, then target `schema`. |
| `table` | Target table name (defaults to `name` if omitted) |
| `expression` | Inline SQL expression (alternative to table reference) |
| `managed` | Set to `true` to bind the source to the `@loader` function of the same name (see [Loaders](/concepts/python-nodes/loaders)) |
| `write_strategy` | How the loader writes data: `table`, `append`, `delete_insert`, or `merge` (requires `managed: true`) |
| `cursor_column` | Column for incremental cursor tracking (required for `delete_insert` and `merge`) |
| `unique_key` | Merge key column(s) (required for `merge`) |
| `freshness` | Source freshness observation config (see [Source freshness](#source-freshness)) |
| `description` | Human-readable description |
| `type_enforcement` | Override implicit type enforcement (`true`/`false`). Defaults to `true` when any column declares a type. |
| `contract` | `enforced` or `none`. When enforced, downstream models validate configured column references against source columns. |
| `columns` | Column declarations with optional types and audits |
| `audits` | Source-level audits |

## Seeds

Source: `concepts/seeds.mdx`

Load static CSV data into your pipeline as tables.

Seeds are CSV files under `seeds/` that SQLBuild loads as tables in the warehouse. They're useful for small, static reference data like lookup tables, category mappings, or configuration values.

### Defining a seed

Place a CSV file in your `seeds/` directory:

```csv
waffle_type_id,waffle_name,category,price_cents
1,Classic Belgian,sweet,850
2,Liege,sweet,950
3,Brussels,sweet,750
4,Cheddar Herb,savory,1050
```

Declare the seed's column types in any `.yml` file under `seeds/`. You can use any filename and organize declarations however you like - one file per seed, or group related seeds together:

```yaml
# seeds/lookups.yml
seeds:
  - name: waffle_types
    description: Waffle menu items with pricing.
    columns:
      - name: waffle_type_id
        type: INTEGER
      - name: waffle_name
        type: VARCHAR
      - name: category
        type: VARCHAR
      - name: price_cents
        type: INTEGER
```

Every seed must have a YAML declaration with at least one typed column. CSV filenames must be unique across the entire `seeds/` directory (including subdirectories). The seed name in the YAML must match the CSV filename (without the `.csv` extension).

### Referencing seeds

Seeds are referenced in models with `__seed()`:

```sql
SELECT
  o.order_id,
  w.waffle_name,
  w.price_cents * o.quantity AS line_total_cents
FROM __ref("stg_orders") o
LEFT JOIN __seed("waffle_types") w ON o.waffle_type_id = w.waffle_type_id
```

`__seed()` is distinct from `__ref()`. Using `__ref()` with a seed name raises a compile error with a message pointing you to `__seed()`.

### Loading seeds

Seeds are loaded automatically during `sqb build`. You can also load them standalone:

```bash
sqb seed
```

Seeds are fully replaced on every run. If the CSV changes, the table is recreated with the new data.

### Target overrides

Seeds inherit the project's default database and schema. You can override these per seed:

```yaml
seeds:
  - name: waffle_types
    database: analytics
    schema: lookups
    columns:
      - name: waffle_type_id
        type: INTEGER
      - name: waffle_name
        type: VARCHAR
```

### CSV settings

For non-standard CSV formats, configure parsing behavior with `csv_settings`:

```yaml
seeds:
  - name: european_prices
    csv_settings:
      delimiter: ";"
      encoding: utf-8
      quotechar: '"'
    columns:
      - name: product_id
        type: INTEGER
      - name: price
        type: VARCHAR
```

#### Available CSV settings

| Setting | Type | Description |
|---------|------|-------------|
| `delimiter` | string | Field delimiter (default: `,`) |
| `quotechar` | string | Character used to quote fields (default: `"`) |
| `doublequote` | boolean | Whether the quotechar is doubled to escape itself |
| `escapechar` | string | Character used to escape the delimiter or quotechar |
| `skipinitialspace` | boolean | Skip whitespace after the delimiter |
| `lineterminator` | string | Line terminator character |
| `encoding` | string | File encoding (default: `utf-8`) |
| `na_values` | list or mapping | Values to treat as null - a global list or per-column mapping |
| `keep_default_na` | boolean | Whether to use the default set of NA values in addition to `na_values` |

#### Per-column NA values

`na_values` can be a flat list (applied to all columns) or a mapping from column names to their NA values:

```yaml
csv_settings:
  na_values:
    price: ["N/A", ""]
    category: ["unknown"]
```

## Overview

Source: `concepts/models.mdx`

SQL model anatomy, references, dependencies, and the model documentation guide.

A model is a SQL file that defines one transformation step and produces a table or view in the warehouse.

### Model anatomy

Every model starts with a `MODEL()` header followed by its query:

```sql
MODEL (
  materialized table,
  tags [marts],
  description "Order fact table",
  columns (
    order_id (type INTEGER, audits [not_null]),
  ),
);

SELECT
  o.order_id,
  o.customer_id,
  p.amount_cents
FROM __ref("stg_orders") o
JOIN __ref("stg_payments") p USING (order_id)
```

The header controls how SQLBuild builds, validates, and documents the model. The query remains ordinary SQL apart from SQLBuild reference and macro calls.

### References

| Reference | Syntax | Resolves to |
|-----------|--------|-------------|
| Model | `__ref("name")` | Another model |
| Seed | `__seed("name")` | A seed CSV table |
| Source | `__source("name")` | An external source |
| Scalar UDF | `__udf("name")` | A user-defined function |

SQLBuild discovers the dependency graph from these calls and orders selected work topologically. Among selected models, upstream models run before downstream dependents. An unselected upstream is read from its existing warehouse relation; use an upstream-expanding selector such as `+fact_orders` when it should also be built. Seeds use `__seed()`, not `__ref()`.

See [Functions](/concepts/functions) for scalar UDF and table-function references.

### Model guide

- [Materializations](/concepts/models/materializations): views, tables, incrementals, snapshots, and custom materializations.
- [Schemas](/concepts/models/schemas): inline columns, reusable schemas, inheritance, audits, and model-local extensions.
- [Type Enforcement](/concepts/models/type-enforcement): static type checks and runtime cast behavior by materialization.
- [Contracts](/concepts/models/contracts): exact and open output validation, runtime guarantees, nullability, and enum-backed columns.
- [Hooks](/concepts/models/hooks): SQL and Python lifecycle hooks.
- [Configuration](/concepts/models/configuration): `MODEL()` field reference and SQL-validation controls.

For deeper execution behavior, see [Incremental](/concepts/incremental), [Snapshots](/concepts/snapshots), and [Audits](/concepts/audits).

## Materializations

Source: `concepts/models/materializations.mdx`

Choose how SQLBuild persists model output.

The `materialized` field selects how a model becomes a warehouse relation.

### View

Creates or replaces a database view on each build:

```sql
MODEL (materialized view);

SELECT id AS order_id, customer_id, status
FROM __source("raw__orders")
```

View audits run after the view has been replaced. A failing audit marks the build as failed but cannot preserve the previous view. Views use compile-time contract and type analysis; SQLBuild does not rewrite the view with runtime casts or run the staged runtime-contract step.

### Table

By default, creates a staging table, applies supported type and contract enforcement, runs blocking audits, and only then promotes it to the destination. A pre-promotion failure leaves the previous destination unchanged.

```sql
MODEL (materialized table);

SELECT customer_id, COUNT(*) AS total_orders
FROM __ref("stg_orders")
GROUP BY customer_id
```

Projects may opt into `settings.table_promotion_mode = "immediate"`. Immediate promotion replaces the destination before audits, so a failed audit does not restore the old table. Immediate promotion rejects models that require declared-type enforcement or `contract enforced`; use staged promotion for those guarantees.

### Incremental

On a normal incremental run, applies append, delete/insert, or merge DML from a staged delta. Delete/insert removes matching keys or cursor ranges before inserting replacement rows. Cursor configuration controls replay bounds and may split work into microbatches.

```sql
MODEL (
  materialized incremental,
  incremental_strategy delete_insert,
  cursor activity_hour,
  cursor_type timestamp,
  cursor_grain hour,
  unique_key [activity_hour],
);
```

For non-microbatch models, the first run, `--full-refresh`, and a full replay-on-change rebuild use the full-table path rather than incremental DML. Microbatch models retain batched execution: a full rebuild drops the existing target, creates its replacement from the first batch, and applies later batches with incremental DML. A failed full-refresh microbatch does not preserve the previous target.

See [Incremental](/concepts/incremental) for cursor semantics, replay, schema changes, and microbatch execution.

### Snapshot

Maintains historical row versions with SCD Type 2 semantics:

```sql
MODEL (
  materialized snapshot,
  unique_key [customer_id],
  snapshot_strategy timestamp,
  updated_at updated_at,
);

SELECT customer_id, name, plan, status, updated_at
FROM __source("customers")
```

See [Snapshots](/concepts/snapshots) for timestamp and check strategies, historical inputs, and full-refresh policies.

### Custom

A project-local Python materialization can manage specialized persistence with adapter access, schema findings, query-change state, declared columns, and `ctx.run_audits`.

```sql
MODEL (
  materialized partition_tracked,
  placeholders (
    partition_start "'2026-04-01'",
    partition_end "'2026-04-05'",
  ),
  config (
    tracking_table partition_state,
    partition_column order_date,
  ),
);

SELECT *
FROM __ref("stg_orders")
WHERE ordered_at >= @@@partition_start
  AND ordered_at < @@@partition_end
```

The `config` block is passed to the Python function through `ctx.config`. Runtime-owned `@@@placeholder` values remain unresolved until materialization execution.

The custom function owns staging, runtime type or contract enforcement, audit timing, promotion, and rollback. Framework final audits run after the function returns unless `MaterializationResult.audit_results` is populated. A custom materialization can call `ctx.run_audits` against a staging relation before applying changes and return those results through `MaterializationResult.audit_results`.

## Schemas

Source: `concepts/models/schemas.mdx`

Declare model columns inline or reuse canonical inherited schemas.

Schema metadata defines column names, types, nullability, descriptions, and column audits. It can live inline in one `MODEL()` header or in a reusable `SCHEMA()` declaration.

### Inline columns

Use inline columns for metadata owned by one model:

```sql
MODEL (
  materialized view,
  description "Cleaned order records",
  columns (
    order_id (type INTEGER, nullable false, audits [not_null, unique]),
    customer_id (type INTEGER, nullable false, audits [not_null]),
    status (
      type VARCHAR,
      audits [accepted_values (values ["placed", "completed", "cancelled"])],
    ),
  ),
);
```

See [Audits](/concepts/audits) for built-in audits, custom audits, arguments, severity, and incremental run scope.

### Reusable schemas

When multiple models implement the same relation shape, declare it once under `schemas/`. SQLBuild discovers schema files recursively and makes public names available throughout the project.

```sql
-- schemas/orders/order.sql
SCHEMA (
  name order,
  description "Canonical staged order shape",
  columns (
    order_id (type INTEGER, nullable false, audits [not_null]),
    customer_id (type INTEGER, nullable false, audits [not_null]),
    status (type VARCHAR),
  ),
);
```

Bind a model with `model_schema`:

```sql
MODEL (
  materialized view,
  schema staging,
  model_schema order,
  contract enforced,
);
```

`schema staging` selects the warehouse destination schema. `model_schema order` selects reusable column metadata.

The reusable description becomes the model description when the model does not declare one. A model-owned description takes precedence.

### Model-local columns

A bound model may add output columns that are not part of the reusable shape:

```sql
MODEL (
  model_schema order,
  columns (
    ingestion_batch_id (type VARCHAR, nullable false),
  ),
  contract enforced,
);
```

Resolved schema columns retain their order and new model-local columns follow them. Use a named child schema when an extension is reusable; use inline columns for an extension owned by one model.

### Model-specific column audits

Audits in a reusable schema apply to every bound model. A model can add stricter audits to an inherited column by naming that column and declaring only `audits`:

```sql
MODEL (
  model_schema order,
  columns (
    order_id (audits [unique]),
  ),
);
```

The effective `order_id` keeps the reusable type, nullability, description, and `not_null` audit, then adds `unique`. A model cannot remove reusable audits or override inherited metadata. An inherited-column entry containing `type`, `nullable`, or `description` fails compilation. Identical audit instances are deduplicated.

### Inheritance

A reusable schema may extend one parent with additional columns:

```sql
SCHEMA (
  name sourced_order,
  extends order,
  columns (
    source (type VARCHAR, nullable false),
  ),
);
```

Inheritance may be transitive. Parent columns resolve before child columns. An inherited column cannot be redeclared or overridden in a child schema. SQLBuild rejects unknown parents, cycles, case-insensitive duplicates, and multiple parents.

Physical SQL output order is not currently enforced. Static contract analysis matches names and checks declared types and proven non-nullability. Runtime exact-contract validation matches names and types but does not validate nullability.

### Contracts and planning

`contract enforced` treats the complete named-plus-local declaration as the exact output shape. An unspecified model follows the project's `column_contract_mode`; `contract none` explicitly keeps the resolved columns as metadata, audit attachment, and type-enforcement inputs without activating shape validation. See [Contracts](/concepts/models/contracts).

For models bound to a reusable schema, effective column names, types, nullability, and enum members participate in model version identity. Changing those fields on a parent therefore affects models bound through descendants. Descriptions do not change model identity. Audits have their own audit-gate identities, so audit changes invalidate reusable audit results without changing the model version itself.

### Limitations

Reusable schemas intentionally support a narrow ownership model:

- One optional parent, with transitive inheritance.
- Additive child and model-local output columns.
- Audit-only model augmentation of inherited columns.
- No general column overrides, multiple inheritance, composition, mixins, parameters, or generated projections.
- No physical output ordinal enforcement.

## Type Enforcement

Source: `concepts/models/type-enforcement.mdx`

Understand declared model types, static checks, and runtime casting.

Type enforcement makes authored column types operational. It is a model feature as well as a related source feature, and it is separate from whether a model uses an exact contract.

### Enabling it

For a SQL model, declaring a type on any inline or reusable-schema column enables type enforcement automatically:

```sql
MODEL (
  materialized table,
  columns (
    order_id (type INTEGER),
    ordered_at (type TIMESTAMP),
    source_system (),
  ),
);
```

There is no `MODEL(type_enforcement ...)` switch. In this example, `order_id` and `ordered_at` are typed; `source_system` remains untyped and passes through unchanged.

Sources have related behavior but different configuration. A source can explicitly set `type_enforcement: false`; see [Sources](/concepts/sources#type-enforcement).

### Compile-time checks

When SQL analysis can infer an output type, SQLBuild compares it with the declared type using adapter-aware normalization. A proven mismatch is a compile error when type enforcement is active. If SQLBuild identifies an output column but cannot prove its expression type, it reports an unproven-type warning rather than guessing. If the entire output shape cannot be inferred, static type checks and warnings cannot run.

Static analysis does not rewrite the authored query. It determines whether the inferred output is compatible before warehouse execution.

### Runtime casting

Runtime enforcement inspects a staged relation. If a typed output column does not already have its declared type, SQLBuild rebuilds the staging or delta relation with an explicit cast:

```sql
CAST(order_id AS INTEGER) AS order_id
```

Only columns with declared types are cast. Untyped output columns are preserved. If a cast fails, the model fails during the type-enforcement phase before the staged table is promoted or the incremental delta is applied.

Runtime cast support currently depends on materialization:

| Materialization path | Framework runtime casts |
|----------------------|-------------------------|
| Full table with staged promotion | Yes, on the staging table |
| Non-microbatch incremental | Yes, on the staged delta |
| Microbatch incremental | Yes, on each staged batch |
| View | No; the view query defines the warehouse output type |
| Snapshot | No framework cast reconstruction |
| Custom materialization | Owned by the custom materialization |
| Full table with immediate promotion | Rejected when type enforcement is required |

Staged promotion is the default table mode. If a project selects immediate table promotion, a typed model fails with guidance to use staged promotion because SQLBuild cannot inspect and reconstruct output before mutating the destination.

### Type enforcement versus contracts

These controls answer different questions:

| Feature | Question |
|---------|----------|
| Type enforcement | Should typed columns be checked and, on supported paths, cast to their declared physical types? |
| `contract none` | Which declared columns can SQLBuild verify statically while still allowing additional output columns? |
| `contract enforced` | Must the output have exactly the complete declared shape? |

Type enforcement can be active with `contract none`. Conversely, an enforced contract may contain untyped columns: exact shape validation still checks their names, but there is no declared physical type to cast or compare.

### Schema changes

Declared types are used in schema-change detection. With type enforcement active, the declared type is authoritative for typed columns when SQLBuild compares a planned model with the warehouse relation.

## Contracts

Source: `concepts/models/contracts.mdx`

Validate required or exact model output schemas.

A model's declared columns provide output metadata, type enforcement, and column audit attachment. The project `column_contract_mode` and model `contract` policy determine whether those declarations also define a statically validated output shape.

| Model declaration | Behavior |
|-------------------|----------|
| Unspecified | Follow `settings.column_contract_mode`: `implicit` validates declared columns as an open shape; `explicit` treats them as metadata and audit attachment only. |
| `none` | Do not activate declared-shape or nullability contract validation for this model. Explicit type enforcement remains active. |
| `enforced` | Treat declared columns as the complete authoritative output shape and enable runtime exact-schema checks on supported materializations. |

The project default is `column_contract_mode = "implicit"`, which preserves SQLBuild's original behavior. Projects that use column declarations primarily for metadata and audits, including migrations from dbt, can opt into explicit contracts:

```toml
[settings]
column_contract_mode = "explicit"
```

Under explicit mode, a model must declare `contract enforced` to activate shape validation. A model-level `contract enforced` or `contract none` always overrides the project mode.

```sql
MODEL (
  materialized table,
  contract enforced,
  columns (
    order_id (type INTEGER, nullable false),
    customer_id (type INTEGER, nullable false),
    amount_cents (type INTEGER),
    status (type VARCHAR),
  ),
);
```

### Validation

#### Compile time

When declared-shape validation is active and SQL analysis can infer the model's output:

- A missing declared column fails.
- A proven type mismatch fails when type enforcement or an exact contract is active.
- A declared non-null column fails when its expression is proven nullable.
- Additional inferred columns fail only for `contract enforced`.

If SQLBuild cannot infer the output shape, these static shape checks cannot run. An enforced contract additionally requires a non-empty column declaration and adds runtime requirements on supported materializations.

Type enforcement remains independent. Typed columns continue to receive static type checks and supported runtime casts under explicit mode and `contract none`.

Configuration fields that reference output columns, including `unique_key`, `cursor`, `updated_at`, and `check_columns`, are checked against an enforced declaration.

#### Runtime

For supported materialization paths, `contract enforced` inspects the staged relation and rejects:

- Missing declared columns.
- Additional undeclared columns.
- Warehouse types that differ from declared types.

Runtime contract validation does not scan data for nulls and does not inspect warehouse nullability metadata. `nullable false` participates in static nullability analysis; add a `not_null` audit when null values must be checked at runtime.

Runtime exact-schema validation currently runs for:

- Staged full-table builds.
- Non-microbatch incremental deltas.
- Snapshot deltas.

Views and custom materializations rely on compile-time contract analysis. Microbatch incrementals currently apply type enforcement and audits but do not perform the framework runtime exact-schema validation step.

Staged table validation happens before promotion, so a failure leaves the existing destination untouched. Immediate table promotion is incompatible with `contract enforced` because SQLBuild cannot validate output before replacing the destination.

### Type enforcement

Declaring a model column type enables type enforcement automatically, independently of the contract policy. Type enforcement controls static type compatibility and runtime casts on supported table and incremental paths; contracts control output shape. See [Type Enforcement](/concepts/models/type-enforcement) for the materialization matrix.

### Reusable schemas

Contracts apply to the effective declaration, not only the reusable base:

```sql
MODEL (
  model_schema order,
  columns (
    ingestion_batch_id (type VARCHAR, nullable false),
  ),
  contract enforced,
);
```

With `contract enforced`, this requires exactly the resolved `order` columns plus `ingestion_batch_id`. With `contract none`, the resolved columns remain metadata, audit attachment points, and inputs to explicit type enforcement without activating shape validation. See [Schemas](/concepts/models/schemas).

### Enum columns

A column may use a declared enum as a portable logical domain type:

```sql
MODEL (
  contract enforced,
  columns (
    market_type (type market_type),
  ),
);
```

This does not require, create, or reference a warehouse-native enum type. SQLBuild resolves string-valued enums to `VARCHAR` and integer-valued enums to `INTEGER`. Under `contract enforced`, it also generates an `accepted_values` audit for the declared members. Audit severity and timing follow normal audit configuration and materialization behavior. With the default error severity, it gates staged-table promotion and pre-DML delta paths; views and custom materializations may already have changed their relation when the audit runs.

Enum member references such as `@enum("market_type").WIN` are a separate feature that render one validated SQL literal. See [Enum Model Contracts](/concepts/enums/model-contracts) for the complete distinction and lowering behavior.

### Related policies

The project default is implicit open-shape validation for models that omit `contract`. A repository can select explicit opt-in contracts with `settings.column_contract_mode = "explicit"` or enable [`SQBKR401`](/concepts/kata#layers-and-model-grammar) to require enforced contracts through Kata architecture policy.

Contracts also constrain schema-change behavior. For example, `snapshot_schema_change append_new_columns` is incompatible with `contract enforced` because an unannounced appended column would violate the exact declaration.

## Hooks

Source: `concepts/models/hooks.mdx`

Run SQL or Python lifecycle hooks around model materialization.

Pre-hooks and post-hooks run before and after model materialization. Use SQL hooks for warehouse statements and Python hooks for runtime control flow, providers, queries, and skip decisions.

### Project layout

SQL and Python hooks live in language-specific directories:

```text
my_project/
  models/
    marts/
      orders.sql
  hooks/
    sql/
      permissions/
        grant_access.sql
      record_access.sql
    python/
      notifications.py
```

Directories below `hooks/sql/` and `hooks/python/` are organizational. They do not namespace resource names: `hooks/sql/permissions/grant_access.sql` is still invoked as `sql("grant_access")`.

### Choose a hook type

<a id="reusable-sql-hooks"></a>
<a id="sql-hook-arguments"></a>
<a id="inline-sql-hooks"></a>
<a id="sql-compilation"></a>
<a id="python-hooks"></a>
<a id="hook-context"></a>
<a id="providers"></a>
<a id="skip-timing"></a>

Hook lists use three explicit entry types:

| Entry | Definition | Use |
|-------|------------|-----|
| [`inline_sql("...")`](/concepts/models/hooks/sql#inline-sql-hooks) | SQL written directly in the model header | Short, model-specific SQL |
| [`sql("name", args...)`](/concepts/models/hooks/sql) | A reusable resource under `hooks/sql/` | Shared, parameterized SQL |
| [`python("name", args...)`](/concepts/models/hooks/python) | A decorated function under `hooks/python/` | Control flow, providers, queries, or skips |

Bare SQL strings are not hook entries. The singular `pre_hook` and `post_hook` fields are also invalid; use `pre_hooks` and `post_hooks` with one of the three typed forms above. `sql("...")` always means a named SQL hook and never falls back to inline SQL.

### Configure model hooks

Models may mix SQL and Python entries in one ordered hook list:

```sql
MODEL (
  materialized table,
  pre_hooks [
    inline_sql("INSERT INTO audit.build_log VALUES ('starting')"),
  ],
  post_hooks [
    sql(
      "grant_access",
      relation: "@@CTX:destination.qualified",
      role: "analyst_role",
    ),
    python(
      "notify_complete",
      channel: "#data-builds",
    ),
  ],
);

SELECT 1 AS id
```

Entries execute in the order authored, including when SQL and Python entries are mixed.

<a id="failure-timing"></a>

### Lifecycle and failure timing

Pre-hooks run before materialization. A failed pre-hook prevents materialization, and a Python pre-hook that returns `ctx.skip(...)` stops the remaining pre-hooks and prevents the model from running.

Post-hooks run after warehouse mutation and audits. They are not promotion gates: a failed post-hook marks the model run as failed, but the relation has already been created, promoted, or incrementally updated. Put logic that must prevent materialization in a pre-hook, contract, pre-promotion audit, or the materialization itself.

A Python post-hook that returns `ctx.skip(...)` stops the remaining post-hooks and changes the reported model result. `mode="hard"` blocks downstream nodes. A soft skip does not automatically block every downstream node; scheduler propagation also depends on the other upstream results.

### Names and identity

SQL and Python hook names share the project-wide resource namespace with models, sources, seeds, functions, loaders, tasks, assets, checks, and providers. Any collision fails discovery, including two same-stem SQL hook files in different directories or a SQL and Python hook with the same name.

The ordered hook list participates in each model's version identity:

- Inline and named SQL hooks contribute their fully rendered statements. Named hooks also retain their resource name, definition, arguments, description, and source path in identity metadata.
- Python hooks contribute the invocation name, configured arguments, and a version hash derived from the decorated function, its transitive first-party dependencies, and decorator configuration.
- Changing a hook body, arguments, or order changes the consuming model's identity and makes it stale for change-aware planning.
- Executed Python hooks record their own hook fingerprints after successful completion or an explicit skip.

Named SQL hooks compile into their consuming models rather than becoming independently scheduled nodes. Python hooks also run as part of their model's lifecycle phase rather than as independently selected Python nodes.

### Diagnostics

Discovery and compilation fail early for malformed definitions and invocations. Diagnostics include the resource path and, for model entries, the model name and indexed label such as `post_hooks[1] sql("grant_access")`.

See the language-specific pages for definition, argument, validation, and runtime diagnostics:

- [SQL hooks](/concepts/models/hooks/sql)
- [Python hooks](/concepts/models/hooks/python)

## SQL Hooks

Source: `concepts/models/hooks/sql.mdx`

Define, parameterize, compile, and invoke reusable or inline SQL lifecycle hooks.

SQL hooks submit one rendered SQL payload to the adapter before or after model materialization. Use a named SQL hook for reusable behavior and `inline_sql(...)` for short model-specific payloads.

For shared lifecycle ordering, failure timing, naming, and identity rules, see the [Hooks overview](/concepts/models/hooks).

### Reusable SQL hooks

SQLBuild discovers `.sql` files recursively under `hooks/sql/`. Each file defines exactly one hook and must start with a `HOOK(...)` header as its first non-whitespace content.

**`hooks/sql/permissions/grant_access.sql`**

```sql
HOOK (
  description "Grant a warehouse role access to the model relation"
);

GRANT SELECT ON @relation TO @role
```

The hook name is always the filename stem, so this resource is invoked as `sql("grant_access", ...)`. Nested directories organize files but do not namespace names: `hooks/sql/admin/grant_access.sql` is still named `grant_access`.

`HOOK()` accepts only an optional, non-empty `description`. It does not accept a `name`; rename the file to rename the hook. The content after the header must be non-empty and becomes the SQL payload for each invocation.

Files beginning with `_` are skipped. All other `.sql` files under `hooks/sql/` are parsed as hook resources and must have a valid `HOOK()` header.

### Invoke a named hook

Pass the hook name and its arguments from a model's `pre_hooks` or `post_hooks` list:

**`models/marts/orders.sql`**

```sql
MODEL (
  materialized table,
  post_hooks [
    sql(
      "grant_access",
      relation: "@@CTX:destination.qualified",
      role: "analyst_role",
    ),
  ],
);

SELECT 1 AS id
```

SQLBuild resource-header fields use native `key value` syntax, as in `TEST (mode macro)`, `SCENARIO (tags ["revenue"])`, `AUDIT (severity error)`, and `HOOK (description "...")`. The `relation: ...` and `role: ...` entries above intentionally retain `key: value` syntax because they are nested named arguments to the `sql(...)` hook call, not resource-header fields. The same distinction applies to named arguments passed to `python(...)`.

### SQL hook arguments

Named SQL hooks declare parameters by using them in the SQL body. Arguments are supplied as named values in `sql("name", args...)`:

| Syntax | Behavior |
|--------|----------|
| `@name` | Raw substitution. Strings are inserted verbatim for relations, identifiers, keywords, or SQL fragments. |
| `@'name'` | SQL-literal substitution. Strings are single-quoted and embedded quotes are escaped. |

**`hooks/sql/record_access.sql`**

```sql
HOOK (
  description "Record access configuration"
);

INSERT INTO audit.access_log (relation_name, role_name)
VALUES (@'relation', @'role')
```

```sql
MODEL (
  post_hooks [
    sql(
      "record_access",
      relation: "@@CTX:destination.qualified",
      role: "O'Brien",
    ),
  ],
);

SELECT 1 AS id
```

For both forms, booleans render as `TRUE` or `FALSE`, numbers render directly, and `null` renders as `NULL`. Lists render as comma-separated values, applying raw or quoted behavior to each item. For example, `@'roles'` with `roles: ["reader", "writer"]` renders as `'reader', 'writer'`.

Every referenced argument is required and every supplied argument must be used. Missing arguments, unused arguments, and unsupported values such as maps fail compilation. Raw string arguments are not escaped; use `@'name'` for data values and reserve `@name` for trusted SQL structure.

### Inline SQL hooks

Use `inline_sql("...")` for SQL that is specific to one model:

```sql
MODEL (
  materialized table,
  post_hooks [
    inline_sql("GRANT SELECT ON @@CTX:destination.qualified TO analyst_role"),
  ],
);

SELECT 1 AS id
```

An inline hook accepts exactly one quoted SQL string and no additional arguments. That string becomes one adapter execution payload.

### Compile-time context

Both named and inline SQL hooks receive the invoking model's runtime context. They support:

- Project variables such as `@@audit_schema`
- Environment variables such as `@@ENV:DEPLOY_ROLE`
- Hook context variables such as `@@CTX:destination.qualified`
- Enums and constants such as `@enum("role").ANALYST` and `@const("retention_days")`
- Python macros such as `@grant_target("@@CTX:destination.qualified")`

For named hooks, SQLBuild first substitutes `@name` and `@'name'` arguments into the hook body. A supplied argument such as `relation: "@@CTX:destination.qualified"` therefore resolves to the invoking model's final target-overridden destination.

An inline hook uses macros, constants, and enums available to its model file. A named hook uses those
available to its own file under `hooks/sql/`. See
[How Visibility Works](/concepts/declaration-scopes/visibility#which-file-controls-visibility).

`${...}` config-template syntax is not valid in SQL hooks.

| Variable | Value |
|----------|-------|
| `@@CTX:destination.qualified` | Fully qualified destination relation |
| `@@CTX:destination.schema` | Destination schema |
| `@@CTX:destination.database` | Destination database |
| `@@CTX:destination.table` | Destination relation name |
| `@@CTX:model.name` | Model name |
| `@@CTX:model.database` | Model database |
| `@@CTX:model.schema` | Model schema |
| `@@CTX:model.alias` | Model alias |
| `@@CTX:run.target` | Active target name |
| `@@CTX:run.id` | Current run ID |

Context components can be combined into qualified identifiers without whitespace or a Python
wrapper:

```sql
HOOK ();

CREATE FUNCTION @@CTX:destination.database.@@CTX:destination.schema.reconstruct_book()
RETURNS INTEGER
LANGUAGE SQL
AS 'SELECT 1'
```

### Validation and diagnostics

SQLBuild strictly validates hook resource syntax, arguments, interpolation, macros, metadata, and non-empty payloads. It does not classify executable statement kinds or implement vendor SQL grammar. Each rendered hook payload is passed to the adapter in one `execute` call; whether a driver accepts multiple statements or client-side batch separators is adapter and warehouse behavior. Use separate hook entries when portable ordering between statements matters.

After expansion, Polyglot validates the complete payload using the active adapter's analysis dialect when the model's effective SQL-validation gate is enabled, which it is by default. SQL analysis must be enabled, `--no-sql-validation` must be absent, and the effective project or model `sql_validation` value must be true. Polyglot does not understand every administrative or procedural command supported by every warehouse. If it cannot parse valid vendor-specific hook SQL, disable SQL validation for that model or invocation and let the adapter and warehouse provide the authoritative result. SQLBuild does not compensate with keyword allowlists or handwritten parser fallbacks.

Common errors include:

- Missing or malformed leading `HOOK(...)` headers
- Unsupported header keys, empty descriptions, and missing SQL bodies
- Missing or unused arguments and unsupported argument values
- Unknown named hooks, unquoted hook names, and bare hook strings
- SQL rejected by Polyglot while optional SQL validation is enabled

Definition errors point to the hook file. Invocation and argument errors also identify the consuming model entry, such as `post_hooks[1] sql("grant_access")`. Runtime output preserves the authored hook index and identifies named and inline SQL entries.

## Python Hooks

Source: `concepts/models/hooks/python.mdx`

Define Python lifecycle hooks with runtime context, providers, SQL access, and skips.

Python hooks run model lifecycle logic that needs Python control flow, providers, warehouse queries, logging, or explicit skip decisions.

For shared lifecycle ordering, failure timing, naming, and identity rules, see the [Hooks overview](/concepts/models/hooks).

### Define a Python hook

SQLBuild discovers decorated functions recursively from `.py` files under `hooks/python/`:

**`hooks/python/notifications.py`**

```python
from sqlbuild.hooks import hook

@hook
def notify_complete(ctx, channel="#data-builds"):
    ctx.log(
        f"Notify {channel}: "
        f"{ctx.model_name} completed during {ctx.phase}"
    )
```

By default, the hook name is the function name. The decorator accepts optional `name` and `description` arguments. A Python file may define multiple decorated hooks.

Files named `__init__.py` or beginning with `_` are skipped. Imported decorated functions are not registered again from the importing module.

### Invoke a Python hook

Reference the hook by name and optionally pass keyword arguments:

```sql
MODEL (
  materialized table,
  post_hooks [
    python(
      "notify_complete",
      channel: "#model-alerts",
    ),
  ],
);

SELECT 1 AS id
```

Python hook arguments are ordinary configuration values and are not SQL-expanded. An argument containing `@@CTX:...` or `@macro()` reaches the function unchanged.

### Signature validation

Unknown hooks, unknown keyword arguments, missing required arguments, required positional-only arguments, and arguments that conflict with context or provider injection fail compilation. A function with `**kwargs` can accept additional configured arguments.

Python hooks must return `None` or `ctx.skip(...)`. Any other return value fails execution.

### Hook context

Python hooks declare a `HookContext` parameter named `ctx`, `context`, `_ctx`, or `hook_context`. It need not be the first parameter when providers or configured arguments are also present:

| Field | Description |
|-------|-------------|
| `ctx.model_name` | Model being built |
| `ctx.phase` | `pre_hooks` or `post_hooks` |
| `ctx.hook_name` | Invoked hook name |
| `ctx.hook_index` | Zero-based position in the authored hook list |
| `ctx.run_id` | Current run ID |
| `ctx.target` | Active target |
| `ctx.vars` | Effective project variables |
| `ctx.destination` | Destination relation metadata |
| `ctx.adapter_name` | Active adapter name |
| `ctx.adapter` | Adapter instance |
| `ctx.connection` | Live connection |
| `ctx.execute_sql(sql)` | Execute SQL |
| `ctx.query(sql)` | Execute SQL and return rows |
| `ctx.log(message)` | Write run output |
| `ctx.skip(reason="...", mode="soft")` | Return a soft or hard skip result; arguments are keyword-only |
| `ctx.providers` | Access discovered [providers](/concepts/python-nodes/providers) |

### Providers

Providers may be injected into Python hook parameters by name or accessed through `ctx.providers`. They are resolved lazily using the same lifecycle as loaders, tasks, assets, and checks. SQL hooks cannot use providers because they are compiled SQL statements rather than Python callables.

```python
from sqlbuild.hooks import hook

@hook
def notify_complete(ctx, slack_notifier):
    slack_notifier.send(
        f"Model {ctx.model_name} built successfully"
    )
```

### Skips and failures

Returning `ctx.skip(...)` stops the remaining hooks in the current phase. Runtime exceptions fail that lifecycle phase. See [Lifecycle and failure timing](/concepts/models/hooks#lifecycle-and-failure-timing) for the effects of pre-hook and post-hook skips, soft and hard modes, and failures after warehouse mutation.

### Identity and diagnostics

Python hook invocations and version hashes participate in model identity as described in [Names and identity](/concepts/models/hooks#names-and-identity). Executed hooks also record their own fingerprints after successful completion or an explicit skip.

Compilation reports unknown hooks and invalid signatures with the model name and indexed invocation label, such as `post_hooks[1] python("notify_complete")`. Runtime output preserves the authored index and hook name. Exceptions and unsupported return values fail with the Python hook identity attached.

## Configuration

Source: `concepts/models/configuration.mdx`

MODEL() header fields and SQL-validation controls.

### Common fields

| Field | Description |
|-------|-------------|
| `materialized` | `view`, `table`, `incremental`, `snapshot`, or a custom materialization name |
| `tags` | Tags used by selectors |
| `description` | Human-readable model description |
| `columns` | Model-local column declarations or inherited-column audit augmentation |
| `model_schema` | Reusable column schema name |
| `audits` | Model-level audit instances |
| `enums` | Model-local enum declarations; names must begin with `_` |
| `constants` | Model-local scalar, list, set, or object constants; names must begin with `_`. Use `constant(...)` for an explicit decimal type or collection rendering override. |
| `schema` | Destination warehouse schema override |
| `database` | Destination database override |
| `alias` | Destination relation-name override |
| `pre_hooks` | Ordered `inline_sql(...)`, `sql("name", ...)`, or `python("name", ...)` hooks before materialization |
| `post_hooks` | Ordered `inline_sql(...)`, `sql("name", ...)`, or `python("name", ...)` hooks after materialization |
| `enabled` | Set to `false` to disable the model |
| `contract` | `none` for an open statically checked declaration, or `enforced` for an exact declaration |
| `sql_validation` | Per-model SQL-validation override |

### SQL validation

SQL validation has two hard gates and one effective setting:

1. `settings.sql_analysis` must be enabled.
2. `--no-sql-validation` must not be present.
3. `MODEL (sql_validation true|false)` overrides `settings.sql_validation` for that model. If omitted, the project setting is used.

The model override can re-enable validation when the project-level `settings.sql_validation` value is false, but it cannot bypass disabled SQL analysis or the CLI kill switch.

### Table fields

| Field | Description |
|-------|-------------|
| `run_despite_unchanged` | Table-only change-aware policy. `always` rebuilds whenever selected. A duration such as `30d`, `12h`, or `90m` rebuilds while the newest timestamp-based upstream source observation is within that age; it is not a periodic schedule. |

Table promotion mode is a project setting rather than a `MODEL()` field. Staged promotion is the default. Immediate promotion is incompatible with model type enforcement and exact contracts; see [Materializations](/concepts/models/materializations#table).

### Incremental fields

| Field | Description |
|-------|-------------|
| `incremental_strategy` | `append`, `delete_insert`, or `merge` |
| `cursor` | Output column used to track incremental position |
| `cursor_type` | `timestamp` or `integer` |
| `cursor_grain` | Timestamp grain such as `second`, `hour`, or `day` |
| `cursor_start` | Lower cursor bound |
| `cursor_inputs` | Upstream names mapped to cursor columns |
| `unique_key` | Merge or delete/insert matching columns |
| `incremental_mode` | Set to `microbatch` for batched execution |
| `batch_size` | Timestamp duration string such as `1d` or `1h`; use a numeric string such as `"1000"` for an integer cursor |
| `lookback` | Backward replay extension |
| `append_cursor_inclusive` | Include (`true`, default) or exclude (`false`) the current append-cursor boundary |
| `merge_exclude_columns` | Columns left unchanged by matched-row merge updates |
| `full_refresh` | Optional model execution override: `false` always runs incrementally, `true` always full-refreshes, and omission follows the command |
| `on_schema_change` | `append_new_columns`, `sync_all_columns`, `ignore`, or `fail` |
| `replay_on_change` | `forward`, `full`, or `bounded-<duration>` |

See [Incremental](/concepts/incremental) for full semantics.

Current compatibility behavior treats an unrecognized `on_schema_change` value as the default `append_new_columns` policy and an unrecognized `replay_on_change` value as `forward`. Use the documented values exactly; future validation may reject unknown values instead of applying these fallbacks.

### Snapshot fields

| Field | Description |
|-------|-------------|
| `unique_key` | Columns identifying one logical record |
| `snapshot_strategy` | `timestamp` or `check` |
| `updated_at` | Source update timestamp for the timestamp strategy |
| `check_columns` | Columns compared by the check strategy, or `[*]` |
| `observed_at` | Observation timestamp for historical inputs |
| `historical_input` | `snapshot` or `changes` |
| `initial_valid_from` | Initial validity policy for first-seen rows |
| `invalidate_hard_deletes` | Close records that disappear from current-state input |
| `valid_from_column` | Override the generated valid-from column name |
| `valid_to_column` | Override the generated valid-to column name |
| `snapshot_full_refresh` | Snapshot full-refresh safety policy |
| `snapshot_schema_change` | Snapshot schema-change policy |

See [Snapshots](/concepts/snapshots) for strategy combinations, defaults, and safety behavior.

### Custom materialization fields

| Field | Description |
|-------|-------------|
| `config` | Arbitrary values passed to `ctx.config` |
| `placeholders` | Defaults for runtime `@@@placeholder` tokens |

### Diff fields

| Field | Description |
|-------|-------------|
| `row_diff_exclude_columns` | Columns excluded from row-level comparison |
| `row_diff_tolerances` | Numeric comparison tolerances |

## Enums

Source: `concepts/enums.mdx`

Define a fixed set of named string or integer values and use them safely in SQL.

Enums give a name to a fixed set of allowed values. SQLBuild checks the enum and every member
reference during compilation, then renders the selected value as a safe SQL literal.

### Create an enum

Put project-wide enums under the top-level `enums/` directory. Files are discovered recursively, so
subdirectories can organize a large enum library without changing where the enums are available.

```text
my_project/
├── enums/
│   ├── market/
│   │   └── market_type.sql
│   └── order_status.sql
├── models/
└── sqlbuild_project.toml
```

```sql
-- enums/market/market_type.sql
ENUM (
  name market_type,
  members [WIN, PLACE, SHOW],
);
```

The shorthand above uses each member name as its string value. Use explicit values when the name
used in SQLBuild should differ from the stored value:

```sql
ENUM (
  name source,
  members (
    CENTRUM "centrum",
    PARISTURF "paristurf",
  ),
);
```

Integer enums always use explicit values:

```sql
ENUM (
  name priority,
  members (LOW 1, HIGH 3),
);
```

### Use an enum member

Reference one member with `@enum("name").MEMBER`:

```sql
SELECT *
FROM prices
WHERE market_type = @enum("market_type").WIN
  AND source = @enum("source").CENTRUM
```

SQLBuild validates the enum name and member name before the query runs. The active adapter safely
renders the underlying string or integer value.

Enum references work in model queries, SQL hooks, SQL functions, audits, unit tests, scenarios, and
inline source expressions.

### Validation rules

- An enum must contain at least one member.
- Every member must use the same value type: all strings or all integers.
- Enum names and member names must be SQL identifiers.
- Member names must be uppercase and lookup is case-sensitive.
- Enum names must be unique across all public enums in the project.
- Project-wide names cannot begin with `_`; that prefix is reserved for model-private values.

Invalid declarations, unknown enums, and unknown members fail compilation.

### More enum features

    Use an enum as a portable model-column domain and generate accepted-value validation.
    Keep an enum inside one model when no other resource should use it.

To limit an enum to one folder, or to that folder and its child folders, see
[Declarations and Scopes](/concepts/declaration-scopes).

## Constants

Source: `concepts/constants.mdx`

Define reusable compiler-validated values and reference them safely from SQL.

Constants give a name to a value used in SQL. SQLBuild validates the value during compilation and
asks the active adapter to render it safely for its SQL dialect. Constant values are data, never raw
SQL snippets.

### Create a constant

Put project-wide constants under the top-level `constants/` directory. Files are discovered
recursively, and one file may contain more than one declaration.

```text
my_project/
├── constants/
│   ├── market/
│   │   └── thresholds.sql
│   └── reporting_day.sql
├── models/
└── sqlbuild_project.toml
```

```sql
-- constants/market/thresholds.sql
CONSTANT (name min_runners, value 7);
CONSTANT (name fallback_source, value "centrum");
CONSTANT (name enabled, value true);
CONSTANT (name ratio, value 0.75);
CONSTANT (name missing_value, value null);
```

Folders below `constants/` are organizational. They do not change where project-wide constants are
available.

### Use a constant

Reference a constant with `@const("name")`:

```sql
SELECT *
FROM prices
WHERE runner_count >= @const("min_runners")
  AND source = @const("fallback_source")
```

References work in model queries, SQL hooks, SQL functions, audits, unit tests, scenarios, and
inline source expressions. An unknown constant fails compilation.

### Scalar values

Constants support strings, signed integers, booleans, finite floating-point numbers, exact
decimals, and `null`. Integers use a portable signed 64-bit range. `NaN` and positive or negative
infinity are rejected.

Use `type decimal` with a quoted value when decimal precision must be exact:

```sql
CONSTANT (
  name usd_rate,
  type decimal,
  value "2.4700",
);
```

SQLBuild parses the quoted value directly as a decimal rather than first converting it to a binary
float. An incompatible `type` and `value` fails compilation.

### Naming rules

Public constant names must be unique among public constants and cannot begin with `_`. Enum,
constant, and macro names use separate namespaces, so an enum and a constant may share a name.

### More constant features

    Define lists, sets, and objects, then choose value-list or native-array rendering.
    Keep a constant inside one model when no other resource should use it.

To limit a constant to one folder, or to that folder and its child folders, see
[Declarations and Scopes](/concepts/declaration-scopes).

## Collections and Rendering

Source: `concepts/constants/collections-and-rendering.mdx`

Define list, set, and object constants and control their adapter-specific SQL rendering.

Constants can hold collections as well as scalar values. Use this page when a constant represents
a reusable value list, native array, set, or structured object.

### Lists

Square brackets declare an ordered list. Lists preserve authored order and allow duplicates:

```sql
CONSTANT (
  name supported_countries,
  value ["GB", "FR", "HK"],
);
```

### Sets

Curly braces declare a set. Sets reject duplicate typed values and use a stable order when SQLBuild
renders or fingerprints them:

```sql
CONSTANT (
  name unique_countries,
  value {"GB", "FR", "HK"},
);
```

`{true, 1}` is valid because a boolean and an integer are different logical types.
`{"GB", "FR", "GB"}` fails compilation instead of silently discarding the duplicate.

### Objects

Parenthesized key-value entries declare a string-keyed object. Values may be scalars, lists, sets,
or other objects:

```sql
CONSTANT (
  name country_rules,
  value (
    GB (
      label "Great Britain",
      threshold 2.47,
      enabled true,
      regions ["ENG", "SCT", "WLS"],
    ),
    FR (
      label "France",
      threshold 2.5,
      enabled true,
      regions ["IDF", "NAQ"],
    ),
  ),
);
```

Object keys must be unique. Objects are logical JSON values rather than portable homogeneous SQL
maps or structs.

### Collection rules

Lists and sets must be non-empty and have one compatible element type. Nullable elements do not
determine the type, so `[1, null, 2]` is valid, while these declarations fail:

```sql
CONSTANT (name empty_values, value []);          -- no element type
CONSTANT (name unknown_values, value [null]);    -- no non-null element type
CONSTANT (name mixed_values, value [1, "two"]); -- incompatible types
```

Objects may contain different value types because each key is checked independently. SQLBuild also
applies nesting-depth, element-count, and rendered-size safety limits.

### Value-list rendering

Lists and sets render as a parenthesized value list by default. This is designed for `IN`:

```sql
WHERE country_code IN @const("supported_countries")
```

```sql
WHERE country_code IN ('GB', 'FR', 'HK')
```

Every element is escaped by the active adapter.

  A value-list constant is intended for a value-list position such as `IN (...)`. It is not a
  portable standalone projection. Use native-array rendering when the constant must be an array
  expression.

### Native-array rendering

Set `render_as array` to request an adapter-native array:

```sql
CONSTANT (
  name supported_countries_array,
  value ["GB", "FR", "HK"],
  render_as array,
);
```

SQLBuild does not rewrite array membership operations. Use the operators and functions provided by
your adapter.

Sets support the same `value_list` and `array` modes as lists. Scalar and object constants reject
`render_as` because those rendering modes do not apply to them.

| Adapter | Native array expression | Object/JSON expression |
|---------|-------------------------|------------------------|
| DuckDB | `['GB', 'FR', 'HK']` | `json('{"GB":"Great Britain"}')` |
| MotherDuck | `['GB', 'FR', 'HK']` | `json('{"GB":"Great Britain"}')` |
| Snowflake | `ARRAY_CONSTRUCT('GB', 'FR', 'HK')` | `PARSE_JSON('{"GB":"Great Britain"}')` |
| BigQuery | `['GB', 'FR', 'HK']` | `JSON '{"GB":"Great Britain"}'` |
| Databricks | `array('GB', 'FR', 'HK')` | `parse_json('{"GB":"Great Britain"}')` |
| PostgreSQL | `ARRAY['GB', 'FR', 'HK']` | `'{"GB":"Great Britain"}'::JSONB` |
| SQL Server | Unsupported | `JSON_QUERY(N'{"GB":"Great Britain"}')` |

BigQuery does not support arrays containing arrays. SQL Server has no native array representation.
Unsupported requests fail compilation rather than silently changing representation.

### Project default

Set the default for list and set constants in `sqlbuild_project.toml`:

```toml
[constants]
collection_rendering = "array"
```

SQLBuild chooses the rendering mode in this order:

1. The declaration's `render_as` field
2. Project `[constants].collection_rendering`
3. The `value_list` default

One constant has one representation throughout a compilation. Changing its value or rendering mode
changes the identity of SQL that uses it.

### Stable values

- List order and duplicates are preserved.
- Set order is ignored; membership is stored in a stable order.
- Object key order is ignored; keys are stored in a stable order.
- Changing set membership or object values changes dependent query identity.

## Enum Model Contracts

Source: `concepts/enums/model-contracts.mdx`

Use an enum as a portable model-column domain with generated accepted-value validation.

An enum can describe the allowed domain of a model column as well as provide individual SQL
literals.

These are separate uses:

- `@enum("market_type").WIN` inserts one validated value into SQL.
- `type market_type` declares that a model column uses the complete enum domain.

### Declare an enum-typed column

Use the enum name as the column type:

```sql
MODEL (
  contract enforced,
  columns (
    market_type (type market_type),
  ),
);
```

SQLBuild does not send `market_type` to the warehouse as a physical type and does not create a
warehouse-native enum. It translates the enum into portable column metadata:

| Enum values | Physical column type | Generated validation |
|-------------|----------------------|----------------------|
| Strings such as `WIN` and `PLACE` | `VARCHAR` | `accepted_values` for the enum strings |
| Integers such as `1` and `3` | `INTEGER` | `accepted_values` for the enum integers |

### Contract behavior

With `contract enforced`, SQLBuild runs the generated `accepted_values` audit with the model's other
audits. Its severity and timing follow the model's ordinary audit and materialization settings.

With `contract none`, SQLBuild still resolves the enum to its portable scalar column type but does
not generate the domain audit.

This behavior is the same on adapters with and without native enum support. The physical warehouse
column remains an ordinary string or integer column.

Changing the members of an enum-typed contract changes the model's contract identity and generated
validation.

## Model-Private Values

Source: `concepts/model-private-values.mdx`

Keep enums and constants inside one model when no other resource should use them.

Put an enum or constant directly in `MODEL()` when it belongs to one model and should not enter the
project-wide namespace.

```sql
MODEL (
  enums (
    _state [OPEN, CLOSED],
  ),
  constants (
    _min_runners 7,
    _supported_countries ["GB", "FR", "HK"],
  ),
);

SELECT *
FROM runners
WHERE state = @enum("_state").OPEN
  AND runner_count > @const("_min_runners")
  AND country_code IN @const("_supported_countries")
```

### Where private values work

A model-private value is available in:

- The owning model's query
- Inline SQL hooks written in that model

It is not available in:

- Another model
- A child or sibling model directory
- A unit test or scenario
- A named SQL hook stored under `hooks/sql/`

Private names begin with exactly one `_`. Names beginning with `__` are reserved for SQLBuild.
Because the model owns the name, different models may each define `_state` without creating a
collision.

### Explicit types and rendering

Use `constant(...)` when a private constant needs an exact type or rendering choice:

```sql
MODEL (
  constants (
    _usd_rate constant(
      type decimal,
      value "2.4700",
    ),
    _supported_countries constant(
      value ["GB", "FR", "HK"],
      render_as array,
    ),
  ),
);
```

### When a value becomes shared

Move the declaration out of `MODEL()` when another resource needs it. Remove the `_` prefix and put
it in the narrowest suitable enum or constant directory. See
[Declarations and Scopes](/concepts/declaration-scopes) for those advanced placement options.

## Writing Macros

Source: `concepts/macros.mdx`

Write Python functions that generate reusable SQL fragments at compile time.

Macros are Python functions that generate SQL during compilation. They provide reusable,
parameterized SQL without introducing a separate template language.

### Create a macro

Put project-wide macros in Python files under the top-level `macros/` directory:

```text
my_project/
├── macros/
│   ├── currency.py
│   └── test_helpers.py
├── models/
└── sqlbuild_project.toml
```

Every public function defined by a macro file becomes callable from SQL:

```python
# macros/currency.py
def cents_to_dollars(expression: str) -> str:
    """Convert a cents expression to dollars."""
    return f"ROUND(CAST({expression} AS DOUBLE) / 100, 2)"
```

### Call a macro from SQL

Use `@macro_name(...)` in a model query:

```sql
MODEL (
  materialized table,
  tags [marts],
);

SELECT
  order_id,
  @cents_to_dollars("amount_cents") AS amount_dollars
FROM __ref("stg_orders")
```

During compilation, SQLBuild replaces the call with the function's returned SQL:

```sql
ROUND(CAST(amount_cents AS DOUBLE) / 100, 2)
```

A macro used directly in SQL must return a string.

### Arguments

Macro calls accept Python literal values:

- Strings: `"value"` or `'value'`
- Numbers: `42`, `3.14`, `-1`
- Booleans: `True`, `False`
- Lists: `[1, 2, 3]`
- Dictionaries: `{"key": "value"}`
- `None`
- The result of another macro call

Positional and keyword arguments are supported:

```sql
@mock_orders(count=5, status="completed")
```

Use quoted strings when passing SQL expressions such as column names. The macro decides how to
place that text into its returned SQL.

### Keep implementation details private

Only public functions owned by the file are exported as macros. Prefix helpers, constants, classes,
and type aliases with `_`:

```python
# macros/orders.py
_DEFAULT_STATUS = "completed"

def _status_filter(status: str) -> str:
    return f"status = '{status}'"

def completed_orders() -> str:
    return _status_filter(_DEFAULT_STATUS)
```

Here, SQL may call `@completed_orders()`. `_status_filter` and `_DEFAULT_STATUS` remain ordinary
Python implementation details.

Imported functions are not re-exported as new macros from the importing file.

### Use macros in tests

Tests are SQL, so they can use macros as reusable fixture generators:

```python
# macros/test_helpers.py
def mock_orders(count: int = 1) -> str:
    rows = [
        f"SELECT {i} AS id, {i * 100} AS customer_id, 'completed' AS status"
        for i in range(1, count + 1)
    ]
    return " UNION ALL ".join(rows)
```

```sql
TEST();

WITH
__source__raw__orders AS (
  @mock_orders(3)
),
__expected__stg_orders AS (
  SELECT 1 AS order_id, 100 AS customer_id, 'completed' AS status
  UNION ALL
  SELECT 2 AS order_id, 200 AS customer_id, 'completed' AS status
  UNION ALL
  SELECT 3 AS order_id, 300 AS customer_id, 'completed' AS status
)
SELECT 1
```

### Use macros in hooks

Macros work inside inline and named SQL hooks:

```python
# macros/permissions.py
def grant_target(target: str) -> str:
    return f"GRANT SELECT ON {target} TO analyst_role"
```

```sql
MODEL (
  post_hooks [inline_sql('@grant_target(@@CTX:destination.qualified)')],
);

SELECT 1 AS id
```

See [SQL Hooks](/concepts/models/hooks/sql) for hook lifecycle and context syntax.

### Where macros work

Macros are supported in:

- Model query SQL
- Inline and named SQL hooks
- Unit tests and scenarios
- Standalone audit SQL
- SQL functions and supported inline source expressions

Macros are not accepted in ordinary `MODEL()` configuration fields. SQL hook entries are the
exception because their contents are SQL.

### Next steps

    Compose macros through Python imports and use adapter or target context.
    Limit a macro to one folder, or to that folder and its child folders.

## Composition and Context

Source: `concepts/macros/composition-and-context.mdx`

Compose macros through Python, use compile context, and understand scoped imports.

Macros are Python functions, so reusable macros should compose through ordinary Python calls. A
macro returns final SQL; SQLBuild does not treat its output as another layer of macro source.

### Compose helpers in one file

Use underscore-prefixed helpers for implementation details that should not be callable from SQL:

```python
# macros/currency.py
def _divide_by_100(expression: str) -> str:
    return f"({expression} / 100.0)"

def cents_to_dollars(expression: str) -> str:
    return f"ROUND({_divide_by_100(expression)}, 2)"
```

Only `cents_to_dollars` is exported as a SQLBuild macro.

Public macros in the same file are also ordinary Python functions and may call one another:

```python
def add_tax(expression: str) -> str:
    return f"({expression} * 1.2)"

def round_money(expression: str) -> str:
    return f"ROUND({expression}, 2)"

def formatted_total(expression: str) -> str:
    return round_money(add_tax(expression))
```

### Compose macros from different files

Import another project macro when it is visible from the importing macro file:

```python
# macros/orders.py
from macros.currency import add_tax, round_money

def formatted_order_total(expression: str) -> str:
    return round_money(add_tax(expression))
```

SQLBuild records the imported macro files as dependencies. It rejects an import when the target
macro is outside the importing file's declaration scope or when imports form a cycle.

Imported functions do not become duplicate exports from the importing file. In the example above,
`add_tax` and `round_money` retain their original identities; only `formatted_order_total` is newly
exported by `orders.py`.

The same visibility direction applies to scoped macros:

- A scoped macro may import a project-wide macro.
- A scoped macro may import a macro available from its own or an ancestor directory.
- A project-wide macro cannot import a narrower macro.
- A macro cannot import from a sibling or unrelated scope.

See [Declarations and Scopes](/concepts/declaration-scopes) when macros are stored under `macros/`
or `_macros/`.

### Macro output is final SQL

Do not return SQL containing another `@macro()` call:

```python
# Invalid: creates another macro-expansion layer.
def formatted_order_total(expression: str) -> str:
    return f"@round_money(@add_tax({expression!r}))"
```

SQLBuild rejects this output. Import and call the Python functions instead:

```python
from macros.currency import add_tax, round_money

def formatted_order_total(expression: str) -> str:
    return round_money(add_tax(expression))
```

This keeps macro behavior readable in Python and ensures one expansion produces final SQL.

### Nested calls written in SQL

The SQL author may explicitly pass one macro's result to another:

```sql
SELECT @round_money(@add_tax("subtotal")) AS order_total
```

SQLBuild evaluates `add_tax` first and passes its returned string to `round_money`. This is not a
second expansion of generated output: both calls are visible in the SQL source.

Inner macros may return any Python value accepted by the outer macro. A macro used directly in SQL
must return a string.

### Macro context

When the first parameter is named `ctx`, SQLBuild passes a `MacroContext` with adapter, target, and
project-variable information:

```python
# macros/datetime.py
def timestamp_trunc(ctx, grain: str, expression: str) -> str:
    if ctx.adapter_name == "bigquery":
        return f"TIMESTAMP_TRUNC({expression}, {grain.upper()})"
    return f"DATE_TRUNC('{grain}', {expression})"
```

| Field | Description |
|-------|-------------|
| `adapter_name` | Active adapter, such as `duckdb` or `snowflake` |
| `sql_analysis_enabled` | Whether SQL analysis is enabled |
| `target_name` | Active target name, when selected |
| `vars` | Effective project variables after project, target, local, and CLI merging |

```python
def schema_qualified(ctx, table: str) -> str:
    schema = ctx.vars.get("schema_prefix", "public")
    return f"{schema}.{table}"
```

Use context when generated SQL genuinely differs by adapter or target. Prefer ordinary parameters
for values that the SQL caller should choose explicitly.

## Interpolation

Source: `concepts/interpolation.mdx`

How SQLBuild processes variables, context, and dynamic content in SQL and config.

SQLBuild uses two syntax layers for dynamic content:

- **`@` syntax** is for any executable SQL - model queries, SQL hooks, tests, audits, and inline source expressions
- **`${...}` syntax** is for config values - project TOML config, MODEL() header fields (excluding SQL hooks), and source/seed YAML declarations

The rule is simple: if it's any SQL that will be executed, it uses `@`. If it's a config value, it uses `${...}`. These layers never mix.

### Syntax reference

| Syntax | Where | Resolved |
|--------|-------|----------|
| `@enum("name").MEMBER` | Executable SQL | Compile time - expands to the validated enum member value |
| `@const("name")` | Executable SQL | Compile time - expands to the named typed scalar, value list, native array, or object expression |
| `@macro(args)` | Model SQL, SQL hooks, tests, audits, inline source expressions | Compile time - expands to macro return value |
| `@@name` | Model SQL, SQL hooks, tests, audits, inline source expressions | Compile time - project variable substitution |
| `@@ENV:NAME` | Model SQL, SQL hooks, tests, audits, inline source expressions | Compile time - environment variable |
| `@@CTX:name` | SQL hooks only | Compile time - destination relation, target, run ID |
| `@@@name` | Model SQL | Preserved for runtime (custom materializations) |
| `@name` / `@'name'` | Named SQL hook bodies | Raw / SQL-literal invocation argument, resolved at compile time |
| `@name` / `@'name'` | Generic audit SQL | Raw / SQL-literal audit argument |
| `${CTX:...}` | TOML/YAML config values | Config compilation |
| `${ENV:...}` | TOML/YAML config values | Config compilation |

`@@CTX:` is intentionally SQL-hook-only. Model SQL describes a relation's data and should not reference its own destination identity. SQL hooks are the operational SQL layer where destination context is useful - grants, logging, post-materialization DDL. Python hooks access the same information through `ctx.destination` on the [`HookContext`](/concepts/models/hooks/python#hook-context) object.

See [Enums](/concepts/enums) and [Constants](/concepts/constants) for reusable validated values. See
[Collections and Rendering](/concepts/constants/collections-and-rendering) for lists, sets, objects,
and adapter-specific rendering.

SQLBuild uses the location of a SQL file to determine which macros, enums, and constants it can
use. Named SQL hooks use their own file location rather than the location of the calling model. See
[How Visibility Works](/concepts/declaration-scopes/visibility) for the complete directory rules.

### Project variables

Project variables use `@@name` syntax in SQL and are defined in `sqlbuild_project.toml` or per-target:

```toml
# sqlbuild_project.toml
[vars]
schema_prefix = "analytics"

[targets.prod.vars]
schema_prefix = "prod_analytics"
```

```sql
SELECT * FROM @@schema_prefix.customers
```

Variables can also be set in `sqlbuild_local.toml` for developer-specific overrides, or passed via the CLI using `--vars` with a JSON object:

```bash
sqb build --vars '{"schema_prefix": "staging_analytics"}'
```

CLI vars take precedence over local and project config vars.

#### JSON vars and nested values

`--vars` accepts full JSON objects. Values can be strings, numbers, booleans, null, arrays, or nested objects:

```bash
sqb build --vars '{"schema_prefix": "staging", "grants": {"primary_role": "analyst"}, "enabled": true}'
```

In SQL interpolation (`@@name`), only top-level scalar values can be used directly. `null` renders as an empty string. If a variable resolves to an array or object, SQLBuild raises a clear error suggesting you use a macro instead.

For nested or complex values, use `ctx.vars` in a macro:

```python
def grant_role(ctx):
    return ctx.vars["grants"]["primary_role"]
```

The macro context receives the full native JSON structure including nested dicts, lists, booleans, numbers, and `None`.

### Environment variables

Environment variables use `@@ENV:NAME` syntax to inject values from the shell environment:

```sql
SELECT *
FROM @@schema_prefix.customers
WHERE source_system = '@@ENV:SOURCE_SYSTEM'
```

If the environment variable is not set, SQLBuild raises a compile error.

### Context variables

Context variables provide access to the current model's destination relation, active target, and run metadata.

**In SQL hooks** (`@@CTX:` syntax):

```sql
post_hooks [inline_sql('GRANT SELECT ON @@CTX:destination.qualified TO analyst_role')],
```

Context components can appear directly beside qualification dots. SQLBuild resolves the longest
available context key before treating the dot as SQL punctuation:

```sql
CREATE FUNCTION @@CTX:destination.database.@@CTX:destination.schema.reconstruct_book()
RETURNS INTEGER
LANGUAGE SQL
AS 'SELECT 1'
```

**In TOML/YAML config values** (`${CTX:...}` syntax):

```toml
[targets.prod]
schema = "${CTX:destination.schema}"
```

Available context variables:

| Variable | Value |
|----------|-------|
| `destination.qualified` | Fully qualified destination relation name |
| `destination.schema` | Destination schema |
| `destination.database` | Destination database |
| `destination.table` | Destination relation name |
| `model.name` | Model name |
| `model.database` | Model database |
| `model.schema` | Model schema |
| `model.alias` | Model alias |
| `run.target` | Active target name |
| `run.id` | Current run ID |

**In macros**, the `MacroContext` object is passed as the first argument when a macro function accepts a `ctx` parameter:

```python
def timestamp_trunc(ctx, grain: str, expr: str) -> str:
    if ctx.adapter_name == "bigquery":
        return f"TIMESTAMP_TRUNC({expr}, {grain.upper()})"
    return f"DATE_TRUNC('{grain}', {expr})"
```

The macro context provides `adapter_name`, `sql_analysis_enabled`, `target_name`, and `vars`.

### Deferred placeholders

Custom materializations can define runtime placeholders using `@@@name` syntax. These are preserved through compilation and resolved by the materialization at execution time:

```sql
WHERE CAST(ordered_at AS DATE) >= CAST(@@@partition_start AS DATE)
  AND CAST(ordered_at AS DATE) < CAST(@@@partition_end AS DATE)
```

### Audit parameters

Generic audit SQL uses `@name` (single `@`, no parentheses) for raw SQL placeholders and `@'name'` for escaped SQL-literal placeholders. These are resolved when the audit is attached:

```sql
SELECT @column
FROM @relation
WHERE @column IS NULL
```

Use the quoted form for values rather than SQL identifiers or expressions:

```sql
WHERE status = @'expected_status'
```

This is distinct from `@@name` (project variables) and `@macro()` (macro calls), so there is no ambiguity. See [Audits](/concepts/audits) for details on generic audit parameters.

### Named SQL hook parameters

Reusable hooks under `hooks/sql/` use `@name` for raw SQL substitution and `@'name'` for escaped SQL-literal substitution. These parameters are supplied by `sql("name", args...)` and resolved before the rest of the hook SQL is compiled. See [SQL hooks](/concepts/models/hooks/sql#sql-hook-arguments) for value rendering and validation rules.

### Compilation order

SQLBuild processes authored SQL in this order:

1. **Config templates** (`${CTX:...}`, `${ENV:...}`) in TOML/YAML config values are resolved during config compilation
2. **Named SQL hook arguments** (`@name` and `@'name'`) are substituted into reusable hook bodies
3. **Project variables** (`@@name`), **environment variables** (`@@ENV:NAME`), and **context variables** (`@@CTX:name` in SQL hooks) are substituted
4. **Enum and constant references** are validated, normalized, and expanded through the active adapter
5. **Macro calls** (`@name(args)`) are expanded
6. **SQL analysis validation** runs against the fully expanded SQL

This means:
- Config templates resolve first, before any SQL processing
- Named SQL hook arguments can contain `@@CTX:...`, `@@ENV:...`, project-variable, declaration, or macro text; model context values describe the invoking model, while declarations and macros in the resulting named hook body resolve from the hook definition path
- Macros see already-substituted variable values in the SQL
- `@@CTX:destination.qualified` in SQL hooks sees the final target-overridden destination name because hooks are expanded after destination naming is fully resolved
- SQL analysis validates the final expanded SQL, catching syntax errors from both vars and macros
- Python hook arguments are not SQL and remain unexpanded

## Functions

Source: `concepts/functions.mdx`

User-defined functions and table functions managed as part of your project.

Functions are SQL or Python definitions under `functions/` that SQLBuild compiles and deploys to the warehouse alongside your models. They participate in the DAG - if a function definition changes, every model that uses it is rebuilt.

### Scalar UDFs

Scalar UDFs return a single value per row. They can be written in SQL or Python.

#### SQL UDFs

Place SQL function files under `functions/sql/`. Each file has a `FUNCTION()` header declaring arguments and return type, followed by a SQL expression body:

```sql
-- functions/sql/udf__is_completed_order.sql
FUNCTION (
  arguments (order_status STRING),
  returns BOOLEAN,
);

order_status = 'completed'
```

#### Python UDFs

Place Python function files under `functions/python/`. Each file has exactly one function decorated with `@udf(...)`:

```python
# functions/python/is_completed_order_py.py
from sqlbuild.functions import udf

@udf(
    arguments={"order_status": "STRING"},
    returns="BOOLEAN",
    runtime_version="3.11",
)
def main(order_status: str | None) -> bool:
    return order_status == "completed"
```

Python UDFs are deployed as warehouse-native functions (Snowflake Python UDFs, BigQuery remote functions, etc.). The `@udf` decorator is used for static discovery only - SQLBuild parses the AST without importing your code.

#### Using scalar UDFs

Reference scalar UDFs in models with `__udf("name")`:

```sql
SELECT
  order_id,
  __udf("udf__is_completed_order")(status) AS is_completed
FROM __ref("stg_orders")
```

The function name is the file stem (filename without extension). `__udf()` resolves to the adapter-native function call at compile time.

### Table functions

Table functions return multiple rows and columns. They are written in SQL under `functions/sql/` with a `returns table(...)` declaration:

```sql
-- functions/sql/table_fn__customer_orders.sql
FUNCTION (
  arguments (p_customer_id INTEGER),
  returns table (
    order_id INTEGER,
    ordered_at TIMESTAMP,
    waffle_name VARCHAR,
    line_total_cents INTEGER,
    order_status VARCHAR,
    is_completed_order BOOLEAN
  )
);

SELECT
  order_id,
  ordered_at,
  waffle_name,
  line_total_cents,
  order_status,
  is_completed_order
FROM __ref("fact_orders")
WHERE customer_id = p_customer_id
```

#### Why table functions exist

Table functions are designed as an alternative to final-layer views for cases where views don't push predicates efficiently. A view over `fact_orders` with a `WHERE customer_id = ?` filter may scan the entire table if the engine doesn't push the predicate down. A table function accepts the filter as an argument and guarantees the predicate is applied at execution time.

#### Managed table function dependencies

Models call managed table functions with `__table_fn("name")(arguments...)`:

```sql
SELECT customer_id, order_id
FROM __table_fn("table_fn__customer_orders")(42)
```

The name must be double quoted and the second argument list is required, including for a zero-argument function. SQLBuild validates that the target exists, is a table function, and receives the declared number of arguments.

The reference creates a typed dependency in the project DAG. Selecting a consuming model also selects the required function, function changes propagate to consumers, and cycles through models and functions are rejected. SQLBuild treats the call as an opaque relation for SQL analysis and uses the function's declared `returns table(...)` columns for star expansion and terminal lineage.

Incremental state still belongs to the consuming model. A table function does not own a cursor interval or retain execution state.

#### Using table functions

Applications and analysts can call the deployed warehouse function directly:

```sql
SELECT * FROM table_fn__customer_orders(42)
```

### References inside functions

SQL functions can reference the same resources as models:

| Reference | Syntax |
|-----------|--------|
| Model | `__ref("model_name")` |
| Seed | `__seed("seed_name")` |
| Source | `__source("source_name")` |
| Scalar UDF | `__udf("function_name")` |
| Table function | `__table_fn("function_name")(arguments...)` |

These references are resolved at compile time and create DAG edges. If a referenced model changes, the function is redeployed.

A SQL function uses macros, constants, and enums available from its file under `functions/sql/`.
See [How Visibility Works](/concepts/declaration-scopes/visibility) to limit declarations to one
function folder or to that folder and its children.

### Change propagation

Functions participate in fingerprint-based change detection. Their identity includes dependencies and declared return contracts in addition to the function body and runtime metadata. If a function changes, SQLBuild redeploys it and marks dependent models as changed.

### Project layout

```
functions/
  sql/
    udf__is_completed_order.sql        # scalar SQL UDF
    table_fn__customer_orders.sql     # table function (returns table)
  python/
    is_completed_order_py.py      # scalar Python UDF
```

### Python UDF options

The `@udf` decorator accepts these keyword arguments:

| Argument | Required | Description |
|----------|----------|-------------|
| `arguments` | Yes | Dict mapping argument names to SQL types |
| `returns` | Yes | SQL return type string |
| `runtime_version` | No | Python runtime version (e.g. `"3.11"`) |
| `entry_point` | No | Function name to use as the entry point (defaults to the decorated function name) |
| `packages` | No | List of Python packages required at runtime |

### Adapter support

All four supported adapters implement SQL UDFs, Python UDFs, and table functions:

| Feature | DuckDB | Snowflake | BigQuery | Databricks |
|---------|--------|-----------|----------|------------|
| SQL UDFs | Yes | Yes | Yes | Yes |
| Python UDFs | Yes | Yes | Yes | Yes |
| Table functions | Yes | Yes | Yes | Yes |

Future adapters may not support all function types. SQLBuild raises a clear error if a function type is unsupported by the configured adapter.

## Incremental Models

Source: `concepts/incremental.mdx`

Cursor-based incremental strategies, microbatch execution, and backfill policies.

Incremental models process only new or changed data instead of rebuilding the entire table. SQLBuild works out where to resume from the current target and input relations, so there is no separate checkpoint store. A retry recomputes its interval from current warehouse state rather than reusing the exact interval of a failed attempt.

### Strategies

#### append

Inserts new rows without modifying existing data. Optionally uses a cursor (read from the target table's highest value) to avoid reprocessing the full source on every run.

```sql
MODEL (
  materialized incremental,
  incremental_strategy append,
  cursor created_at,
  cursor_type timestamp,
  cursor_grain second,
  append_cursor_inclusive true,
);

SELECT id, customer_id, created_at
FROM __source("raw_events")
```

When `append_cursor_inclusive` is `true` (the default), the lower bound uses `>=`, which may duplicate the boundary row but avoids missing late-arriving data with the same cursor value. Set to `false` for an exclusive (`>`) lower bound if your cursor values are guaranteed unique.

Append without a cursor is also valid. The model simply inserts all rows from the source query on every run.

#### delete_insert

Deletes rows in the cursor range, then inserts the new delta. Requires either `cursor` or `unique_key`.

```sql
MODEL (
  materialized incremental,
  incremental_strategy delete_insert,
  unique_key [order_id],
  cursor order_id,
  cursor_type integer,
);

SELECT order_id, customer_id, order_status, ordered_at, line_total_cents
FROM __ref("fact_orders")
```

With a cursor, `delete_insert` removes rows where the cursor column falls within the replay window, then inserts the new delta. With a `unique_key` only, it deletes matching rows by key before inserting.

#### merge

Upserts rows using a unique key. Matched rows are updated; unmatched rows are inserted.

```sql
MODEL (
  materialized incremental,
  incremental_strategy merge,
  unique_key [customer_id],
  cursor last_ordered_at,
  cursor_type timestamp,
  cursor_grain second,
  cursor_inputs (
    fact_orders ordered_at,
  ),
);

SELECT
  customer_id,
  MAX(ordered_at) AS last_ordered_at,
  COUNT(*) AS total_orders,
  SUM(line_total_cents) AS total_revenue_cents
FROM __ref("fact_orders")
GROUP BY customer_id
```

`merge` always requires `unique_key`. The cursor controls which upstream rows are scanned; the unique key determines how they're matched against the target.

### Full-refresh overrides

Incremental models can override command-level full-refresh behavior with `full_refresh`:

| Model setting | Normal command | Command with `--full-refresh` |
|---------------|----------------|-------------------------------|
| omitted | incremental | full refresh |
| `full_refresh false` | incremental | incremental |
| `full_refresh true` | full refresh | full refresh |

Use `full_refresh false` for models that must retain their normal cursor or microbatch execution even when a broader job requests full refresh:

```sql
MODEL (
  materialized incremental,
  incremental_strategy delete_insert,
  full_refresh false,
  cursor event_date,
  cursor_type timestamp,
  cursor_grain day,
);
```

The override is evaluated per model, so one selection can contain incrementally executed opt-outs and full-refreshed models. It controls execution mode rather than acting as a safety rejection: an opted-out model does not abort the rest of the build.

This does not skip initial loading. If the destination relation does not exist, an incremental or microbatch model still builds the history required by its cursor policy. Cloning an existing destination before the build can provide a current watermark and avoid a first-run historical replay.

### Cursors

Cursors define the incremental replay boundary. SQLBuild queries `MAX(cursor)` from the target table and `MIN/MAX` from upstream inputs to compute the replay window automatically. Observed maxima are inclusive warehouse values; SQLBuild advances them once to produce an effective exclusive end bound.

| Field | Description |
|-------|-------------|
| `cursor` | Output column used to track incremental position |
| `cursor_type` | `timestamp` or `integer` |
| `cursor_grain` | Time grain for timestamp cursors: `second`, `minute`, `hour`, `day`, `month`, `year` |
| `cursor_start` | Lower bound floor; the cursor will never replay before this value |
| `cursor_inputs` | Map of upstream ref/source names to their cursor columns |

#### cursor_inputs

When a model references multiple upstream inputs, `cursor_inputs` is required to tell SQLBuild which column on each input carries the cursor:

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
);
```

SQLBuild uses these to determine the replay window. With multiple listed inputs, the end is the conservative common watermark: the minimum of their maxima. This prevents a faster input from advancing the model beyond data available from a slower input.

On a first build, SQLBuild derives the interval from the declared cursor inputs and cursor policy. If it cannot establish a valid interval, the build fails before mutating the destination.

#### Cursor bounds in model SQL

Cursor-based incremental models can read their effective interval with zero-argument intrinsics:

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
);

SELECT customer_id, ordered_at AS activity_hour
FROM __ref("fact_orders")
WHERE ordered_at >= __cursor_start()
  AND ordered_at < __cursor_end()
```

`__cursor_start()` is the effective inclusive start and `__cursor_end()` is the effective exclusive end after cursor floors, lookback, replay policy, and command-line overrides have been applied. The intrinsics accept no arguments and are only valid in built-in cursor incremental model query SQL. They are rejected in functions, hooks, audits, SQL tests and scenarios, source expressions, non-incremental or cursorless models, custom materializations, and non-microbatch full refreshes.

In microbatch mode, the intrinsics resolve to each batch's concrete bounds. A microbatch full refresh discovers its range from current inputs while ignoring the old destination watermark.

##### Listed inputs bound the window; unlisted inputs do not

Only the inputs you list in `cursor_inputs` bound the replay window. This is an explicit choice, and it has two consequences worth understanding:

- **Listed inputs** drive the window. Their new data advances the `MAX`, which is what tells SQLBuild how far to reprocess and which rows of the target to rewrite.
- **Unlisted inputs are read in full.** SQLBuild does not add a cursor filter to them, and they do not bound the window. This is correct for lookup or dimension tables that have no meaningful cursor column: you do not list them, and SQLBuild reads them whole rather than trying to filter on a column that may not exist.

The implication for `delete_insert` and `merge`: the target rows that get rewritten are the ones whose cursor falls inside the window derived from the listed inputs. If an unlisted input changes in a way that should affect target rows outside that window, those rows are not rewritten on a normal incremental run. List every input whose new data should drive reprocessing; leave unlisted only the inputs you intend to read in full.

To capture changes that fall outside the normal forward window, see [Lookback](#lookback) for late-arriving data and [Replay on change](#replay-on-change) for model changes.

#### Lookback

Lookback extends the start of the replay window backwards to re-process recent data. The cursor is forward-moving, so use lookback to capture late-arriving or backfilled records that land just behind the current position:

```sql
MODEL (
  materialized incremental,
  incremental_strategy delete_insert,
  cursor event_date,
  cursor_type timestamp,
  cursor_grain day,
  lookback 3d,
);
```

With `lookback 3d`, the replay window starts 3 days before the normal cursor position, ensuring that any late-arriving data within that window is picked up.

### Microbatch execution

For large incremental ranges, microbatch mode splits the replay window into configurable batches. Each batch is processed serially with its own audit cycle: create delta, run delta audits, apply DML, clean up.

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
);
```

Without microbatch mode, the entire replay range is processed in one pass.

#### Batch size

`batch_size` controls the window size for each batch. For timestamp cursors, use duration strings like `1d`, `6h`, `1mo`. For integer cursors, use an integer value.

#### Watermark batch limits

Watermark microbatch models can declare what to do when their resolved range contains more batches than an ordinary run should process:

```sql
MODEL (
  materialized incremental,
  incremental_strategy delete_insert,
  incremental_mode microbatch,
  microbatch_strategy watermark,
  cursor_watermark_mode all,
  cursor event_date,
  cursor_type timestamp,
  cursor_grain day,
  batch_size 1d,
  microbatch_limit (
    max_batches 7,
    action cap_from_end,
  ),
);
```

| Action | Behavior when the range exceeds `max_batches` |
|--------|------------------------------------------------|
| `error` | Fail before hooks or model mutation |
| `warn` | Emit a prominent warning and execute the full range |
| `cap_from_start` | Execute the earliest N aligned batches and defer later work |
| `cap_from_end` | Execute the latest N aligned batches ending at the resolved watermark and defer older work |

A cap changes only the work selected for that invocation. Deferred batches are not recorded as complete. `cap_from_end` is useful for feeds where keeping the latest projection current is more important than catching up oldest-first; `cap_from_start` is the oldest-first catch-up policy.

For `cap_from_start`, `max_batches` must be large enough to cover the model's ordinary lookback/current buckets and at least one forward batch. SQLBuild rejects a static limit that cannot make forward progress, including when an idempotent strategy uses its implicit one-batch lookback.

When another watermark model consumes a capped model, SQLBuild uses the producer's durable partition-completion facts as the authoritative availability intervals. A configured producer `cursor_end` remains a domain boundary, but neither that declaration nor the target table's physical `MIN`/`MAX` envelope proves that deferred or intervening intervals were materialized. This keeps disjoint `cap_from_end` suffixes disjoint for downstream execution. If completion history is unavailable, the consumer fails closed.

The project can also set an outer safety policy:

```toml
[microbatches.limits]
max_batches = 100
action = "error" # or "warn"
```

Project limits support only `error` and `warn`; they never silently cap work. When a model has a nested `microbatch_limit`, the project policy checks the full resolved range first and the model policy then applies.

`--max-microbatches N` is an invocation-wide, hard `error` ceiling and an explicit one-run authorization. It takes precedence over project and model limits, applies to models without a declared limit, and never inherits `cap_from_start` or `cap_from_end`. For example, passing a value large enough for an intentional backfill authorizes the full range instead of retaining the model's ordinary-run cap.

The legacy scalar `max_microbatches` model field remains supported as a fail/warn guard. New models should use the nested form when the action is part of the model's execution policy.

#### Mixed-grain chains

When a downstream microbatch model reads from an upstream model with a coarser time grain, SQLBuild aligns the replay to the coarsest participating grain (the model's own grain and its cursor-input grains). This happens on every run that resolves cursor bounds from upstream models, not only when something changes. It is independent of the `replay_on_change` cascade behavior described below.

Alignment does two things: it floors the replay window edges to the coarsest grain, and it coarsens the batch size to that grain. For example, an hourly model downstream of a daily model processes in day-sized batches, so each batch lines up with a unit of upstream data that actually advances instead of producing empty or boundary-straddling windows:

```sql
-- Upstream: daily grain, 2d batches
MODEL (
  materialized incremental,
  incremental_strategy delete_insert,
  cursor activity_day,
  cursor_type timestamp,
  cursor_grain day,
  cursor_inputs (
    hourly_order_activity activity_hour,
  ),
  incremental_mode microbatch,
  batch_size 2d,
);

-- Downstream: hourly grain, but aligns to day automatically
MODEL (
  materialized incremental,
  incremental_strategy delete_insert,
  cursor activity_hour,
  cursor_type timestamp,
  cursor_grain hour,
  cursor_inputs (
    daily_activity_rollup activity_day,
  ),
  incremental_mode microbatch,
  batch_size 6h,
);
```

### Replay on change

When a model's version identity changes (query, config, upstream cascade, or any other change reason), `replay_on_change` is the explicit, per-model policy for how much data to reprocess. Reprocessing is a policy you set, not an automatic forced rebuild, so a definition change does not silently trigger a full rebuild of large downstream tables. You choose the cost per model:

| Value | Effect |
|-------|--------|
| `forward` | Run the normal incremental delta from the cursor (default) |
| `full` | Full table rebuild |
| `bounded-14d` | Replay the last 14 days of data |

The bounded duration supports `d` (days), `h` (hours), `m` (minutes), and `s` (seconds). For example: `bounded-7d`, `bounded-24h`, `bounded-30m`.

```sql
MODEL (
  materialized incremental,
  incremental_strategy delete_insert,
  cursor activity_hour,
  cursor_type timestamp,
  cursor_grain hour,
  replay_on_change full,
);
```

See [Cascade propagation](/concepts/planning/cascade-propagation) for how replay policies propagate through the DAG and how downstream models can override inherited replay behavior.

#### on_schema_change

Controls how schema differences are handled at execution time when the incremental delta has different columns than the target table:

| Value | Effect |
|-------|--------|
| `append_new_columns` | Add new columns to the target table (default) |
| `sync_all_columns` | Add, drop, and alter columns to match the delta |
| `ignore` | Log and continue without schema changes |
| `fail` | Reject the build with an error |

## Overview

Source: `concepts/planning.mdx`

How SQLBuild decides what to build: fingerprints, change reasons, and warehouse-native state.

When you run `sqb plan` or `sqb build`, SQLBuild compiles your project, compares it against the current warehouse state, and produces a plan. By default, SQLBuild runs your full selection - the same predictable behavior as a plain build, with nothing to configure.

Change-aware pruning is opt-in and requires [virtual environments](/concepts/virtual-environments). In a virtual environment, pass `--changes-only` (or set `changes_only = true` in config) to narrow the run to only stale work - unchanged models, seeds, audits, and Python nodes are then skipped. The fingerprints and change reasons below are recorded on every successful build regardless, so change detection is ready the moment you enable pruning.

### What is tracked

Every node in the graph has a versioned identity stored in `_sqlbuild_fingerprints` in the target schema. The planner reads these on every run and compares them against the compiled project.

#### Models and functions

Each model and function has a **fingerprint** derived from:

- **Query hash** - the normalized SQL after macro expansion and reference resolution.
- **Config hash** - version-identity config values (materialization settings, contracts, ordered rendered SQL hooks, Python hook invocations and version hashes, custom config/placeholders).
- **Function hashes** - for models that depend on user-defined functions, the function's own fingerprint is included. A function change cascades to all dependent models.

#### Seeds

Seeds are fingerprinted by content hash and load-affecting config. Unchanged seeds are not reloaded.

#### Python nodes

Loaders, tasks, assets, checks, and Python hooks are fingerprinted by source-code hash, transitive project-dependency hashes (scoped to the git root, so third-party package changes don't count), and decorator config. A Python hook's version hash is also included in every model that invokes it. Reusable SQL hooks are compiled into each consuming model, so their rendered statements participate directly in model identity.

Python identity tracking is primarily a **visual indicator** in the plan: when a node's identity changes, the plan shows source and dependency diffs. Unlike SQL models, the framework can't observe a Python node's external inputs (an API, a file, a service), so skip/run decisions are **user-controlled** via `ctx.skip()` - the node's own logic decides whether it needs to run. See [Python node pruning](#python-node-pruning).

#### Audits

Audits that already passed for the same model version identity are not re-run. When a model's version changes, its audits are re-validated.

### Change reasons

The plan assigns a reason to each node that needs work:

| Reason | Meaning |
|--------|---------|
| First run | No fingerprint exists in the target schema |
| Query changed / checksum changed | The model's query SQL differs from the stored fingerprint (the plan can show a query diff) |
| Config changed | Version-identity config values differ |
| Schema changed | Upstream schema changes detected (column additions, removals, type changes) |
| Upstream changed | An upstream model's change cascades downstream (see [Cascade propagation](/concepts/planning/cascade-propagation)) |
| Run despite unchanged | The model is configured to run periodically even without changes (see [Run despite unchanged](#run-despite-unchanged)) |

By default, every selected node runs regardless of its reason. Under `--changes-only`, nodes with no pending work are pruned and show as current in the plan output.

### Changes-only mode

Change-aware pruning requires virtual environments (`virtual_environments = true`); it is rejected in direct mode. Within a virtual environment, `--changes-only` narrows the scope to only models that are actually stale:

```bash
sqb build --virtual-env pr_123 --changes-only
sqb build --virtual-env pr_123 --select path:models/marts --changes-only
sqb plan --virtual-env pr_123 --changes-only
```

To make it the default for a project or target, set it in config instead of passing the flag every run:

```toml
[settings]
virtual_environments = true
changes_only = true

[targets.dev]
changes_only = true
```

The CLI flag takes precedence, followed by the selected target, explicit local settings, then project settings. When any source enables it, the planner removes models and functions from the selected scope if they have no pending work; models with any change reason, a pending backfill, or a changed upstream source are kept. Sources, seeds, and other non-model resources are always kept. See [Virtual Environments: Building](/concepts/virtual-environments/building).

### On this topic

- [Cascade propagation](/concepts/planning/cascade-propagation) - how a change signal propagates downstream, and how each materialization type responds.
- [Source freshness](/concepts/planning/source-freshness) - observing whether external source data has actually changed between runs.
- [Selection and staleness](/concepts/planning/selection-and-staleness) - how `--select` interacts with change detection, and the stale warnings that prevent silent partial rebuilds.

### Run despite unchanged

Some models depend on external data that isn't tracked by source freshness, for example a table model that reads from an API-populated staging area. `run_despite_unchanged` forces a model to run periodically even when its version identity hasn't changed.

```sql
MODEL (
  materialized table,
  run_despite_unchanged "always",
);
```

- **`always`** - run on every build regardless of state.
- **Duration** (e.g. `24h`, `30d`, `90m`) - run if at least the specified time has passed since the model's upstream source freshness was last observed. Requires at least one upstream source with timestamp freshness tracking.

Only table materializations support `run_despite_unchanged`. When triggered, downstream models are also marked as stale.

### Python node pruning

When unchanged SQL models are skipped, read-side Python nodes (tasks, assets, checks) that depend on those models are also skipped. Loaders always run regardless of pruning, since they populate sources that the SQL graph depends on.

Python nodes also have their own identity fingerprints: if a node's source code or dependencies change, it runs even if its SQL dependencies haven't.

### Warehouse-native state (direct mode)

In direct mode, all change-tracking state lives in the warehouse as append-only tables in the same schemas as your data:

- **`_sqlbuild_fingerprints`** - version identities for models, functions, seeds, and Python nodes. One row per successful build per identity.
- **`_sqlbuild_source_freshness`** - source freshness observations. One row per successful build per source identity.
- **`_sqlbuild_node_results`** - Python node runtime results (payload, metadata, status, errors). One row per execution per node.

There is no external state database, no manifest files, and no state machine with transitions that can corrupt. The planner reads the latest row per identity, compares it against the compiled project, and writes new rows after successful builds. Old rows are retained as immutable history.

State tables are read across all target schemas in the project, so fingerprints and freshness observations resolve consistently regardless of which schema a model targets.

Use `sqb janitor` to prune old state history rows while retaining the latest per identity.

### Virtual environments

Virtual environments store identities and change-tracking state in the VDE state backend (PostgreSQL or DuckDB) rather than in warehouse fingerprint tables, scoped per environment. See [Virtual Environments: Building](/concepts/virtual-environments/building).

## Cascade propagation

Source: `concepts/planning/cascade-propagation.mdx`

How a change signal propagates downstream through the DAG, and how each materialization type responds.

When a model or function changes, the change signal propagates downstream through the DAG. Every model downstream of a changed node is marked `Upstream changed` in the plan, even if its own SQL and config are identical.

The cascade walk is topological: it processes models in dependency order, so each model sees the resolved state of all its upstreams before deciding its own effective action.

### What cascades

- A query, config, or schema change on any model cascades to all its downstream dependents.
- A function change cascades to every model that calls it (directly or transitively).
- Source freshness changes propagate downstream the same way. See [Source freshness](/concepts/planning/source-freshness).

### How materialization types respond

- **Views** are recreated on every build regardless, so a cascade has no extra cost.
- **Tables** are fully rebuilt, same as if they had changed themselves.
- **Incremental models** receive a replay window from the cascade. A `full` replay always cascades. A `bounded` replay only cascades when the upstream and downstream models share the same `cursor_type` (e.g. both use `timestamp`), so unrelated cursor types don't inherit bounded windows that don't apply. The downstream model's own `replay_on_change` policy takes precedence over any cascaded signal.

### Resolution when multiple upstreams are stale

If a model has multiple stale upstreams with different replay actions, the most aggressive action wins. `full` beats `bounded`, and among bounded actions, the longer duration wins. Ties are broken alphabetically by model name for determinism.

### Overriding cascaded replay

Downstream incremental models can set their own `replay_on_change` policy to override the cascaded signal. If a downstream model declares its own policy, that policy applies instead of the upstream's. If it has no policy, it inherits the upstream's replay scope.

### Replay on change

When a change is detected on an incremental model, `replay_on_change` controls how much data to reprocess:

- **`forward`** (default) - run the normal incremental delta from the cursor. No reprocessing.
- **`bounded-<duration>`** (e.g. `bounded-14d`) - replay the specified window of data.
- **`full`** - drop and rebuild the entire table.

See [Incremental Models: Replay on change](/concepts/incremental#replay-on-change) for configuration details.

## Source freshness

Source: `concepts/planning/source-freshness.mdx`

Observing whether external source data has actually changed between runs, so downstream models can be skipped when sources are unchanged.

Source freshness lets SQLBuild observe whether external source data has actually changed between runs. Under [`--changes-only`](/concepts/planning#changes-only-mode), models downstream of unchanged sources are skipped; on a default full build the observations are still recorded so pruning is accurate the next time you enable it.

### Configuration

Source freshness is configured per source in `sources/*.yml` with a `freshness:` block. See [Sources: Source freshness](/concepts/sources#source-freshness) for the full configuration reference.

### How observations work

During planning, SQLBuild observes the current data version of each source that has freshness configured (or that the adapter can observe automatically):

1. **Observe** - query the source's current data version using the configured strategy.
2. **Compare** - compare the observed version against the last recorded observation from `_sqlbuild_source_freshness` in the target schema.
3. **Propagate** - walk the DAG downstream from changed or unknown sources to identify which models are affected.

Sources without explicit `freshness:` config are auto-observed using the `adapter` strategy if the adapter supports table metadata and the source has a physical table (not an expression source, not a managed source).

### Lag tolerance

For timestamp-based freshness, `lag_tolerance` controls how much the observed value can drift before being considered a real change. If the current timestamp is within the tolerance of the previous observation, the source is treated as unchanged. This is useful for sources where the freshness timestamp moves by seconds or minutes on every query but the underlying data hasn't meaningfully changed.

### State storage

Source freshness observations are stored in `_sqlbuild_source_freshness` in each target schema. Records are appended only after the affected downstream models build successfully. If a build fails, the previous observation is preserved so the next run still sees the source as changed.

Observations are resolved across all target schemas in the project, so a source referenced by models in different schemas is tracked consistently.

Use [`sqb freshness`](/cli/freshness) to observe source freshness on demand without triggering a build.

## Selection and staleness

Source: `concepts/planning/selection-and-staleness.mdx`

How selection interacts with change detection, and the stale warnings that stop silent partial rebuilds.

Change detection is selection-aware. When you scope a run with `--select`, SQLBuild only runs (and only displays) the resources you selected, but it still reasons about the *whole* graph to keep the result honest. The key case it handles: a selected model whose upstream changed but is **not** in the selection.

### Only selected resources appear in the plan

For a scoped run like `sqb dbt build --select agg_daily_revenue`, the plan shows only the selected resources, not their passive upstream closure. SQLBuild still walks upstreams internally for change propagation (a selected model flips to run when an upstream changed), but those passive upstreams are not listed as plan entries or counted in the header.

`--full-refresh` is likewise scoped to the selected models, not the expanded upstream closure.

### Stale warnings instead of silent partial rebuilds

If a selected model has an upstream that changed but is **outside the selection**, rebuilding the selected model alone would run it on top of a stale upstream and silently produce a result that looks current but isn't. SQLBuild does not do that. It leaves the selected model current (it is not rebuilt) and emits a stale warning naming the changed upstreams, with the selector you can use to incorporate them.

Suppose `stg_orders` (upstream) changed, and you select only the downstream `agg_daily_revenue`:

```bash
sqb dbt plan --select agg_daily_revenue
```

```
Plan ready (1 selected resources)

dbt (1 selected resources)
  planned models: 0 run, 1 current, 0 blocked

  Model plan
    Current (1)
      model.jaffle_analytics.agg_daily_revenue  no change

Warnings (1)
  - selected dbt model 'agg_daily_revenue' is stale: upstream stg_orders changed
    but will not be rebuilt or is stale; rebuild with a closure selector
    (e.g. +model) to incorporate it
```

The model stays current rather than being rebuilt on a stale input, and the warning tells you exactly which upstreams changed and how to pull them in.

### Incorporating the changed upstreams

Use a closure selector to include the changed upstreams in the run. With `+agg_daily_revenue`, SQLBuild pulls in the changed `stg_orders`, cascades the change through the intermediate models, and rebuilds:

```bash
sqb dbt plan --select +agg_daily_revenue
```

```
Plan ready (8 selected resources)
  planned models: 5 run, 1 current, 0 blocked

  Model plan
    Checksum changed (1)
      model.jaffle_analytics.stg_orders         checksum changed
    Upstream changed (4)
      model.jaffle_analytics.agg_daily_revenue  upstream changed
      model.jaffle_analytics.fct_orders         upstream changed
      model.jaffle_analytics.int_order_payments upstream changed
      model.jaffle_analytics.stg_order_statuses upstream changed
```

### Seeds follow the same rule

Seed changes are tracked the same selection-aware way. A changed seed that is outside the current selection does not trigger a partial rebuild of its dependents; instead the dependents are left current and a stale warning is emitted, exactly as for models. This keeps a scoped run from quietly building on a seed that the run didn't reload.

### Why this matters

A run that reports success but silently built a model on stale inputs is a correctness hazard - the data looks fresh but isn't. Surfacing staleness as an explicit warning (and refusing the misleading partial rebuild) keeps scoped runs honest: you either get a result built on current inputs, or a clear warning telling you it would not be, with the fix.

## Snapshots (SCD Type 2)

Source: `concepts/snapshots.mdx`

Preserve row history over time using SCD Type 2 semantics with timestamp or check-based change detection.

Snapshot models maintain historical row versions with validity windows. They answer questions like: what does this entity look like now, what did it look like before, when did it change, and was it absent during a period.

### How snapshots work

SQLBuild adds two generated columns to the target table:

| Column | Meaning |
|--------|---------|
| `valid_from` | When this version became valid (inclusive) |
| `valid_to` | When this version stopped being valid (exclusive). `NULL` means currently active. |

A point-in-time query uses the interval `valid_from <= point_in_time < valid_to`.

### Change detection strategies

#### Timestamp strategy

Use when your source has a reliable column recording when the entity changed.

```sql
MODEL (
  materialized snapshot,
  unique_key [customer_id],
  snapshot_strategy timestamp,
  updated_at updated_at,
);

SELECT
  customer_id,
  name,
  plan,
  status,
  updated_at
FROM __source("customers")
```

If the source `updated_at` is newer than the active target row's `updated_at`, SQLBuild closes the old version and inserts the new one. If `updated_at` is unchanged or older, nothing happens.

#### Check strategy

Use when the source does not have a reliable update timestamp.

```sql
MODEL (
  materialized snapshot,
  unique_key [customer_id],
  snapshot_strategy check,
  check_columns [name, plan, status],
);

SELECT
  customer_id,
  name,
  plan,
  status
FROM __source("customers")
```

SQLBuild compares `check_columns` between source and active target rows. If any checked value differs, a new version is created. Changes to unchecked columns are ignored.

`check_columns [*]` checks all output columns except `unique_key` and the generated validity columns. Explicit columns are recommended for important models to avoid noisy history from volatile metadata columns.

### Historical input

By default, SQLBuild treats the model query as returning the current state of each entity (one row per `unique_key`). When your source contains historical observations over time, add `observed_at` to switch to historical mode.

#### Historical check snapshot

Use for daily full exports or periodic snapshots without a business update timestamp.

```sql
MODEL (
  materialized snapshot,
  unique_key [customer_id],
  snapshot_strategy check,
  check_columns [plan, status],
  observed_at snapshot_date,
);

SELECT
  customer_id,
  plan,
  status,
  snapshot_date
FROM __source("customers_daily_snapshot")
```

Each `observed_at` group is treated as a complete picture of the source at that time. Consecutive unchanged observations are collapsed into a single version.

#### Historical timestamp snapshot

Use for historical observations that include a business update timestamp.

```sql
MODEL (
  materialized snapshot,
  unique_key [customer_id],
  snapshot_strategy timestamp,
  updated_at updated_at,
  observed_at extract_date,
  historical_input snapshot,
);

SELECT
  customer_id,
  plan,
  status,
  updated_at,
  extract_date
FROM __source("customers_historical_extracts")
```

Each row means: "at `extract_date`, the source's current state for this key had this `updated_at`." Validity windows use `updated_at`, not `observed_at`.

#### Historical change records

Use for CDC tables, audit logs, or historical backfills where rows are individual version records.

```sql
MODEL (
  materialized snapshot,
  unique_key [customer_id],
  snapshot_strategy timestamp,
  updated_at updated_at,
  observed_at loaded_at,
  historical_input changes,
);

SELECT
  customer_id,
  plan,
  status,
  updated_at,
  loaded_at
FROM __source("customers_cdc")
```

Multiple changes for the same key in one batch are allowed. `updated_at` determines version ordering. `observed_at` is arrival/load time, not validity time.

#### Historical input rules

| Strategy | `historical_input` | Source shape | Uniqueness | Hard deletes |
|----------|-------------------|-------------|-----------|-------------|
| `check` | `snapshot` (default) | Complete observations over time | `unique_key + observed_at` | Allowed |
| `timestamp` | `snapshot` | Complete observations with update timestamp | `unique_key + observed_at` | Allowed |
| `timestamp` | `changes` | Individual change/version records | `unique_key + updated_at` | Not allowed |
| `check` | `changes` | Not supported | - | - |

Timestamp snapshots with `observed_at` require `historical_input` to be set explicitly.

### Hard deletes

```sql
invalidate_hard_deletes true,
```

When enabled, active target rows whose keys are missing from the source are closed:

- **Current-state input**: closed at execution time
- **Historical input** (`historical_input snapshot`): closed at the `observed_at` time of the group where the key is missing

Hard deletes are not allowed with `historical_input changes` because change-record batches are not complete source snapshots - a missing key just means no change, not deletion.

Reappearing keys create a new active version.

### Configuration reference

| Field | Required | Description |
|-------|----------|-------------|
| `materialized snapshot` | Yes | Enables snapshot lifecycle |
| `unique_key` | Yes | Column(s) identifying one entity |
| `snapshot_strategy` | Yes | `timestamp` or `check` |
| `updated_at` | Timestamp only | Source column with business update time |
| `check_columns` | Check only | Columns compared to detect changes. Use `[*]` for all non-key columns. |
| `observed_at` | No | Source column with observation/extract time. Presence enables historical mode. |
| `historical_input` | Conditional | `snapshot` or `changes`. Required for timestamp with `observed_at`. Defaults to `snapshot` for check with `observed_at`. |
| `invalidate_hard_deletes` | No | Close active rows missing from source. Default `false`. |
| `valid_from_column` | No | Override generated column name. Default `valid_from`. |
| `valid_to_column` | No | Override generated column name. Default `valid_to`. |
| `initial_valid_from` | No | First-version start time: `updated_at`, `observed_at`, or `execution_time`. See defaults below. |
| `snapshot_full_refresh` | No | Model-level full-refresh safety: `deny`, `require_confirmation`, or `allow`. |

#### Initial valid_from defaults

| Case | Default |
|------|---------|
| Timestamp, no `observed_at` | `updated_at` |
| Timestamp, with `observed_at` | `updated_at` |
| Check, no `observed_at` | `execution_time` |
| Check, with `observed_at` | `observed_at` |

### Full refresh safety

Snapshot full refresh can permanently discard history that cannot be reconstructed from the source. SQLBuild guards against this with configurable safety policies.

#### Project config

```toml
[snapshots]
current_state_full_refresh = "deny"
historical_full_refresh = "require_confirmation"
```

| Policy | Behavior |
|--------|----------|
| `deny` | Full refresh is blocked regardless of CLI flags |
| `require_confirmation` | Requires `--allow-snapshot-full-refresh` flag or interactive confirmation |
| `allow` | No snapshot-specific confirmation required |

#### Defaults

| Snapshot type | Default policy | Reason |
|--------------|---------------|--------|
| Current-state (no `observed_at`) | `deny` | Cannot reconstruct older history from current-state source |
| Historical (with `observed_at`) | `require_confirmation` | Can reconstruct if query returns full history, but SQLBuild cannot prove that |

#### Model override

The model `snapshot_full_refresh` field can only make the policy **stricter** than the project setting. A model cannot weaken `deny` to `allow`.

```sql
MODEL (
  materialized snapshot,
  ...
  snapshot_full_refresh deny,
);
```

#### CLI usage

```bash
# Fails if any selected snapshot has effective policy 'deny'
sqb build --full-refresh

# Satisfies 'require_confirmation' policy (cannot override 'deny')
sqb build --full-refresh --allow-snapshot-full-refresh
```

### Audits

Snapshot models support the same audit system as other materializations. Audits with `delta_and_final` run scope execute against the snapshot delta relation before target mutation, blocking promotion if an error-severity audit fails. Final audits run after target mutation.

```sql
MODEL (
  materialized snapshot,
  unique_key [customer_id],
  snapshot_strategy timestamp,
  updated_at updated_at,
  columns (
    customer_id (audits [not_null (run_scope delta_and_final)]),
  ),
);
```

### Duplicate handling

SQLBuild fails with an actionable error if the source query produces duplicate rows at the snapshot identity grain:

- Current-state: duplicate `unique_key`
- Historical snapshot: duplicate `unique_key + observed_at`
- Historical changes: duplicate `unique_key + updated_at`

Deduplicate in your model SQL:

```sql
WITH ranked AS (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY customer_id, snapshot_date
      ORDER BY loaded_at DESC
    ) AS rn
  FROM __source("customer_daily")
)

SELECT customer_id, plan, status, snapshot_date
FROM ranked
WHERE rn = 1
```

### Querying snapshots

#### Current rows

```sql
SELECT * FROM customer_snapshot WHERE valid_to IS NULL
```

#### Point-in-time

```sql
SELECT *
FROM customer_snapshot
WHERE customer_id = 1
  AND TIMESTAMP '2026-02-15' >= valid_from
  AND (valid_to IS NULL OR TIMESTAMP '2026-02-15' < valid_to)
```

#### Fact-to-dimension historical join

```sql
SELECT
  o.order_id,
  o.ordered_at,
  c.plan
FROM orders o
JOIN customer_snapshot c
  ON o.customer_id = c.customer_id
 AND o.ordered_at >= c.valid_from
 AND (c.valid_to IS NULL OR o.ordered_at < c.valid_to)
```

### Examples

#### Composite key

```sql
MODEL (
  materialized snapshot,
  unique_key [user_id, role_id],
  snapshot_strategy check,
  check_columns [role_name, role_status],
  observed_at snapshot_date,
  invalidate_hard_deletes true,
);

SELECT
  user_id, role_id, role_name, role_status, snapshot_date
FROM __source("user_role_daily")
```

#### Custom validity column names

```sql
MODEL (
  materialized snapshot,
  unique_key [product_id],
  snapshot_strategy timestamp,
  updated_at modified_at,
  valid_from_column effective_from,
  valid_to_column effective_to,
);

SELECT
  product_id, name, price, modified_at
FROM __source("products")
```

## Audits

Source: `concepts/audits.mdx`

Data quality checks that run before data reaches the target table.

Audits are SQL queries that verify data quality. If an audit returns rows, something is wrong. SQLBuild runs audits *before* data is promoted to the target table, so bad data never reaches production.

### How audits work

An audit is a SELECT query that returns rows that violate a condition. Zero rows means the audit passes. Any rows returned means a failure.

For `error` severity audits:
- **Full table builds:** SQLBuild materializes into a staging table, runs audits against it, and only promotes to the target if all audits pass. If any fail, the staging table is kept for inspection and the production table is untouched.
- **Incremental models:** Delta-phase audits validate each batch before DML is applied. If an audit fails, the batch is not applied.

For `warn` severity audits, the build continues and the failure is reported in the output.

### Built-in audits

SQLBuild includes four generic audits out of the box. You do not need to define these in `audits/generic/` - they are available automatically:

| Audit | Description | Parameters |
|-------|-------------|------------|
| `not_null` | Fails if any row has a NULL value in the column | Column-level only |
| `unique` | Fails if any non-NULL value appears more than once | Column-level only |
| `accepted_values` | Fails if any non-NULL value is not in the allowed list | `values` - list of allowed values |
| `relationships` | Fails if any non-NULL value does not exist in the referenced column | `to` - target relation, `field` - target column |

#### Using built-in audits

Attach them in the `MODEL()` header like any generic audit:

```sql
MODEL (
  materialized view,
  tags [staging],
  columns (
    order_id (audits [not_null, unique]),
    customer_id (audits [not_null]),
    status (
      audits [
        accepted_values (values ["placed", "preparing", "ready", "completed", "cancelled"]),
      ],
    ),
    payment_method (
      audits [
        relationships (to "stg_payments", field "method"),
      ],
    ),
  ),
);
```

#### Overriding built-in audits

If you define a generic audit with the same name as a built-in (e.g. `audits/generic/not_null.sql`), your definition takes precedence. SQLBuild emits a warning so you're aware of the override:

```
warning[P003]: project audit 'not_null' overrides built-in audit 'not_null'
```

### Custom generic audits

Beyond the built-ins, you can define reusable SQL templates under `audits/generic/`. They use `@parameter` placeholders that are resolved by the audit engine at compile time.

```sql
-- audits/generic/expression_is_true.sql
AUDIT ();

SELECT *
FROM @relation
WHERE NOT (@expression)
```

#### Audit parameters

Generic audit SQL uses `@name` for parameter placeholders. These are resolved by the audit engine, not the general SQL interpolation system:

| Parameter | Description |
|-----------|-------------|
| `@column` | The column name (auto-populated for column-level audits) |
| `@relation` | The target relation (auto-populated from the attached model or source) |
| `@'name'` | A quoted parameter passed from the audit declaration (e.g. `@'values'`) |
| `@name` | An unquoted parameter passed from the audit declaration (e.g. `@expression`) |

Generic and singular audit SQL uses macros, constants, and enums available from the audit file under
`audits/`, not from a model or source that uses the audit. See
[How Visibility Works](/concepts/declaration-scopes/visibility).

#### Attaching custom generic audits

```sql
MODEL (
  materialized table,
  audits [
    expression_is_true (
      name "revenue_is_non_negative",
      expression "total_revenue_cents >= 0",
    ),
  ],
);
```

### Singular audits

Singular audits are standalone SQL files. Their canonical home is `audits/singular/`, and they
reference models directly. They're useful for one-off checks that don't fit a reusable template.
For backward compatibility, singular audits directly under `audits/` or another non-`generic`
child directory continue to compile.

```sql
-- audits/singular/orders_have_payments.sql
AUDIT (
  name "completed_orders_have_payments",
  severity error
);

SELECT o.order_id
FROM __ref("fact_orders") o
LEFT JOIN __ref("stg_payments") p ON o.order_id = p.order_id
WHERE p.payment_id IS NULL
  AND o.order_status = 'completed'
```

SQLBuild automatically infers which model a singular audit attaches to based on the `__ref()` calls in the query. If the audit references a single model, it attaches to that model. If it references multiple models, SQLBuild attaches it to the latest (most downstream) model in the DAG. If attachment can't be inferred, the audit runs at the end of the build.

### Source audits

Sources support the same audit system as models. Audits attached to sources run *before* any dependent model is built:

```yaml
sources:
  - name: raw__orders
    columns:
      - name: id
        audits:
          - not_null
          - unique
    audits:
      - expression_is_true:
          name: no_future_orders
          expression: "ordered_at <= CURRENT_TIMESTAMP"
```

If a source audit with `error` severity fails, all downstream models that depend on that source are blocked. This lets you catch data quality issues at the source before any transformations run.

### Severity

| Severity | Behavior |
|----------|----------|
| `error` | Blocks the build. Staging table is not promoted, DML is not applied. |
| `warn` | Reports a warning but allows the build to continue. |

Set the default severity in `sqlbuild_project.toml`:

```toml
[settings]
default_audit_severity = "warn"
```

Override per audit instance in the `MODEL()` header:

```sql
columns (
  order_id (audits [not_null (severity error)]),
),
```

### Run scope

Audits on incremental models can run at different lifecycle phases:

| Scope | Behavior |
|-------|----------|
| `final` | Run once against the staged table before promotion (default). |
| `delta_and_final` | Run against each delta batch before DML, then again against the target after all batches complete. |

```sql
MODEL (
  materialized incremental,
  ...
  columns (
    activity_hour (audits [not_null (run_scope delta_and_final)]),
  ),
  audits [
    expression_is_true (
      name "orders_placed_is_non_negative",
      expression "orders_placed >= 0",
      run_scope delta_and_final,
    ),
  ],
);
```

Delta-phase audits with `error` severity block DML before the target is updated. This is visible in the build output as `audit (d)` for delta-phase and `audit (f)` for final-phase:

```
  10/13  table     hourly_order_activity  (delete_insert)                OK     0.16s
           audit (d) expression_is_true                                  PASS  4/4
           audit (d) not_null (activity_hour)                            PASS  4/4
           audit (f) expression_is_true                                  PASS
           audit (f) not_null (activity_hour)                            PASS
```

The `4/4` indicates the audit passed for all 4 microbatch batches.

If a model is not incremental, `delta_and_final` degrades to `final` automatically.

### Running audits standalone

```bash
sqb audit
```

This runs all audits without rebuilding any models.

Standalone audits run serially unless concurrency is configured explicitly, through
`SQLBUILD_CONCURRENCY`, or in project settings. For example, `sqb audit --concurrency 8` runs up
to eight selected audits at once, using one warehouse connection per active worker. Increase this
limit deliberately because parallel queries can increase warehouse load and cost. See
[`sqb audit`](/cli/audit) for precedence, ordering, and cancellation details.

## Testing

Source: `concepts/testing.mdx`

SQL unit tests and multi-model tests with macro support, assertions, and model chaining.

SQLBuild supports SQL-native unit tests that validate model logic by comparing actual query results against expected values. Tests can chain across multiple models (multi-model tests), use macros for reusable mock data, and include zero-row assertions.

For end-to-end testing across many models with physical warehouse relations, see [Scenarios](/concepts/scenarios).

### How tests work

A test file defines mock inputs and expected outputs using CTEs. SQLBuild substitutes the mock data into the real model SQL, executes it, and compares the result against the expected CTE using `EXCEPT` queries. Zero mismatched rows means the test passes.

```sql
-- tests/unit/test_stg_orders.sql
TEST();

WITH
__source__raw__orders AS (
  SELECT
    1 AS id,
    100 AS customer_id,
    2 AS waffle_type_id,
    3 AS quantity,
    '2026-04-01 10:00:00' AS ordered_at,
    'completed' AS status
),
__expected__stg_orders AS (
  SELECT
    1 AS order_id,
    100 AS customer_id,
    2 AS waffle_type_id,
    3 AS quantity,
    '2026-04-01 10:00:00' AS ordered_at,
    'completed' AS status
)
SELECT 1
```

The test:
1. Mocks the `raw__orders` source with the `__source__raw__orders` CTE
2. Runs the real `stg_orders` model SQL with the mock substituted in
3. Compares the output against `__expected__stg_orders`
4. Passes if row counts match and there are zero mismatched rows

The trailing `SELECT 1` is required as a ceremonial closing statement.

### CTE conventions

| Prefix | Purpose |
|--------|---------|
| `__source__<name>` | Mock a source. Replaces `__source("<name>")` in the model SQL. |
| `__ref__<name>` | Mock a model. Replaces `__ref("<name>")` in the model SQL. |
| `__seed__<name>` | Mock a seed. Replaces `__seed("<name>")` in the model SQL. |
| `__expected__<name>` | Define expected output for a model. SQLBuild resolves the model's real SQL and compares against this. |
| `__assert__<name>` | Zero-row assertion. Passes if the query returns no rows; fails with the returned rows as diagnostics. |
| `__macro__<name>` | Mock a macro. Replaces every `@<name>(...)` call with the mock value. |

Any CTE without one of these prefixes is treated as a helper CTE, available to all mock and model SQL in the test.

### Multi-model tests

Tests can span multiple models in a single file. Mock your sources, define an expected output for the model you care about, and SQLBuild automatically resolves every intermediate model using its real SQL.

```sql
-- Mock two sources, assert on the final mart.
-- stg_orders and stg_payments resolve automatically from their real SQL.
TEST();

WITH
__source__raw__orders AS (
  SELECT 1 AS id, 100 AS customer_id, 2 AS waffle_type_id, 3 AS quantity,
         '2026-04-01 10:00:00' AS ordered_at, 'completed' AS status
),
__source__raw__payments AS (
  SELECT 1 AS payment_id, 1 AS order_id, 1500 AS amount_cents,
         'credit_card' AS method, '2026-04-01 10:01:00' AS paid_at, 'success' AS status
),
__expected__fact_orders AS (
  SELECT 1 AS order_id, 100 AS customer_id, 1500 AS payment_amount_cents,
         'credit_card' AS payment_method
)
SELECT 1
```

SQLBuild topologically sorts the expected models, resolves each intermediate model's real SQL with mocks substituted, and chains the outputs forward. Every model between the mocked sources and the expected model is computed automatically.

### Mocking refs and seeds

You can mock models directly with `__ref__<name>` and seeds with `__seed__<name>`, not just sources. This skips the model's real SQL (or the seed's real CSV data) and provides controlled data instead:

```sql
TEST();

WITH
__ref__stg_orders AS (
  SELECT
    1 AS order_id,
    100 AS customer_id,
    2 AS waffle_type_id,
    3 AS quantity,
    CAST('2026-04-01 10:00:00' AS TIMESTAMP) AS ordered_at,
    'completed' AS status
),
__ref__stg_payments AS (
  SELECT
    10 AS payment_id,
    1 AS order_id,
    2850 AS amount_cents,
    'card' AS payment_method,
    CAST('2026-04-01 10:05:00' AS TIMESTAMP) AS paid_at,
    'success' AS payment_status
),
__seed__waffle_types AS (
  SELECT
    2 AS waffle_type_id,
    'Liege' AS waffle_name,
    'sweet' AS category,
    950 AS price_cents
),
__expected__fact_orders AS (
  SELECT
    1 AS order_id,
    100 AS customer_id,
    2 AS waffle_type_id,
    'Liege' AS waffle_name,
    'sweet' AS waffle_category,
    3 AS quantity,
    2850 AS line_total_cents,
    CAST('2026-04-01 10:00:00' AS TIMESTAMP) AS ordered_at,
    'completed' AS order_status,
    TRUE AS is_completed_order,
    'card' AS payment_method,
    'success' AS payment_status,
    2850 AS payment_amount_cents
)
SELECT 1
```

You can mix `__source__`, `__ref__`, and `__seed__` mocks in the same test. As long as every leaf dependency is satisfied (either by a source mock, a ref mock, a seed mock, or by being in the expected chain), the test resolves.

### Multiple expected models

A single test can assert on multiple models. SQLBuild resolves and compares each one independently:

```sql
TEST();

WITH
__source__raw__orders AS (
  SELECT 1 AS id, 100 AS customer_id, 2 AS waffle_type_id, 3 AS quantity,
         '2026-04-01 10:00:00' AS ordered_at, 'completed' AS status
),
__source__raw__payments AS (
  SELECT 1 AS payment_id, 1 AS order_id, 1500 AS amount_cents,
         'credit_card' AS method, '2026-04-01 10:01:00' AS paid_at, 'success' AS status
),
__source__raw__customers AS (
  SELECT 100 AS id, 'Leslie' AS first_name, 'Knope' AS last_name,
         'leslie@pawnee.gov' AS email, '2026-01-15 09:00:00' AS created_at
),
__expected__fact_orders AS (
  SELECT 1 AS order_id, 100 AS customer_id, 1500 AS payment_amount_cents,
         'credit_card' AS payment_method
),
__expected__dim_customers AS (
  SELECT 100 AS customer_id, 1 AS total_orders, 1500 AS lifetime_spend_cents
)
SELECT 1
```

If the expected models form a chain (e.g. `stg_orders` feeds into `fact_orders` which feeds into `dim_customers`), SQLBuild resolves them in dependency order, using the output of earlier steps as input to later ones.

When a test defines `__expected__model_name` output, it may also use the public enums and constants
available to that model. A test that checks several models may use the public enums and constants
available to each of them. Public names are unique, so those values cannot conflict.

Only explicit expected CTEs create grants. A matching test filename, `__ref__` mock, or nearby model path does not. Model-private declarations and macros are never granted through expected models.

### Macro-powered mocks

Because unit tests are written in SQL, they support macro calls. This lets you write reusable mock generators instead of copy-pasting mock data across test files:

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
)
SELECT 1
```

The `@mock_orders()` call expands at compile time to whatever SQL the Python macro function returns.

Test SQL uses macros, enums, and constants available from the test file's directory under
`tests/unit/`. Public enums and constants available to a model are also available when the test
defines `__expected__model_name` output for that model. Model-private values are not available to
tests. See [How Visibility Works](/concepts/declaration-scopes/visibility#tests-and-expected-output).

### Macro mocking

When a model uses macros that you want to control in tests (e.g. target-specific logic, dynamic SQL generation), you can override their output with `__macro__<name>` CTEs:

```sql
TEST();

WITH
__macro__country_filter AS (
  SELECT 'country_code = ''US'''
),
__source__raw__orders AS (
  SELECT 1 AS id, 100 AS customer_id, 'US' AS country_code, 'completed' AS status
),
__expected__stg_orders AS (
  SELECT 1 AS order_id, 100 AS customer_id, 'completed' AS status
)
SELECT 1
```

When a `__macro__` mock is defined, every call to `@country_filter(...)` in any model SQL resolved by the test is replaced with the mock value (`country_code = 'US'`). The macro's actual Python function is not called, and the arguments are ignored.

The mock value must be a single `SELECT` with one string literal. Use doubled single quotes for quotes within the value (standard SQL escaping).

This is useful for:
- Testing models that use target-specific macros without depending on target config
- Controlling dynamic SQL generation to produce predictable test inputs
- Isolating model logic from macro implementation details

### Assertions

Unit tests can include `__assert__<name>` CTEs for property-based checks. An assertion passes if the query returns zero rows - any returned rows are failing examples.

```sql
TEST();

WITH
__ref__stg_orders AS (
  SELECT 1 AS order_id, 100 AS customer_id, 3 AS quantity,
         CAST('2026-04-01 10:00:00' AS TIMESTAMP) AS ordered_at, 'completed' AS status
),
__assert__order_ids_are_not_null AS (
  SELECT * FROM __ref("stg_orders") WHERE order_id IS NULL
)
SELECT 1
```

Assertions can be mixed with `__expected__` CTEs in the same test, or used on their own. They are useful when the natural check is "no rows should violate this rule" rather than "the output should exactly equal these rows" - for example, duplicate checks, negative-value constraints, or conditional business rules.

During `sqb test` and `sqb build`, assertion results appear as nested check rows alongside expected comparisons.

### Test modes

By default, `TEST()` runs in model mode - mocking sources/refs and comparing model outputs. Three additional modes let you test reusable logic directly without needing a model chain.

#### Macro tests

Test macro output by calling the macro in `__macro_actual__` and comparing against `__macro_expected__`:

```sql
TEST (mode macro, name "calculates_line_total_cents");

WITH
input_values AS (
  SELECT 950 AS price_cents, 3 AS quantity
),
__macro_actual__ AS (
  SELECT @line_total_cents("price_cents", "quantity") AS line_total_cents
  FROM input_values
),
__macro_expected__ AS (
  SELECT 2850 AS line_total_cents
)
SELECT 1
```

Macros are compile-time code, so macro tests expand the macro at compile time and compare the results. During `sqb build`, macro tests run before any model that uses the tested macro.

#### UDF tests

Test scalar UDFs by calling them in `__udf_actual__` and comparing against `__udf_expected__`:

```sql
TEST (mode udf, name "detects_completed_orders");

WITH
input_values AS (
  SELECT 'completed' AS order_status
  UNION ALL
  SELECT 'pending' AS order_status
),
__udf_actual__ AS (
  SELECT
    order_status,
    __udf("udf__is_completed_order")(order_status) AS is_completed_order
  FROM input_values
),
__udf_expected__ AS (
  SELECT 'completed' AS order_status, TRUE AS is_completed_order
  UNION ALL
  SELECT 'pending' AS order_status, FALSE AS is_completed_order
)
SELECT 1
```

UDFs are warehouse objects, so the function is created before the test runs. During `sqb build`, UDF tests run after the function is created but before any model that uses it.

#### Table function tests

Test table functions by calling them in `__table_fn_actual__` and comparing against `__table_fn_expected__`:

```sql
TEST (mode table_fn, name "returns_customer_orders");

WITH
__table_fn_actual__ AS (
  SELECT order_id, order_status, is_completed_order
  FROM __table_fn("table_fn__customer_orders")(1)
),
__table_fn_expected__ AS (
  SELECT 1 AS order_id, 'completed' AS order_status, TRUE AS is_completed_order
  UNION ALL
  SELECT 2 AS order_id, 'completed' AS order_status, TRUE AS is_completed_order
)
SELECT 1
```

Table function tests run after the function is created. Since table functions are terminal (models cannot depend on them), these tests validate the function independently.

#### Mode rules

Each mode has strict CTE validation:

| Mode | Actual CTE | Expected CTE | Allowed |
|------|-----------|--------------|---------|
| `model` (default) | existing model-chain syntax | `__expected__<model>` | `__source__`, `__ref__`, `__seed__`, `__assert__`, `__macro__` |
| `macro` | `__macro_actual__` | `__macro_expected__` | Helper CTEs, `@macro()` calls in actual |
| `udf` | `__udf_actual__` | `__udf_expected__` | Helper CTEs, `__udf()` calls in actual |
| `table_fn` | `__table_fn_actual__` | `__table_fn_expected__` | Helper CTEs, `__table_fn()` calls in actual |

CTE prefixes from other modes are not allowed. For example, `__source__` in a macro test or `__macro_actual__` in a model test will produce a clear error pointing you to the right mode. Expected CTEs must not call macros, UDFs, or table functions - they should be independent, inspectable expected data.

### Multiple tests per file

A single test file can contain multiple `TEST()` blocks. Each block must have a unique `name`:

```sql
TEST (name "completed_orders_only");

WITH
__source__raw__orders AS (
  SELECT 1 AS id, 100 AS customer_id, 'completed' AS status
),
__expected__stg_orders AS (
  SELECT 1 AS order_id, 100 AS customer_id, 'completed' AS status
)
SELECT 1

TEST (name "cancelled_orders_excluded");

WITH
__source__raw__orders AS (
  SELECT 1 AS id, 100 AS customer_id, 'cancelled' AS status
),
__expected__stg_orders AS (
  SELECT 1 AS order_id, 100 AS customer_id, 'cancelled' AS status
)
SELECT 1
```

A file with a single test can omit the `name` field. Files with multiple tests require names on every block.

### Repeating test logic

SQLBuild supports three repetition patterns:

| Pattern | Use when | Result identity |
|---------|----------|-----------------|
| Multiple `TEST` blocks | Cases need different SQL shapes | One result per block |
| Macro or `VALUES` case table | One aggregate comparison is sufficient | One result for the table |
| Native parameters and cases | Cases share a template but need independent status | One result per named case |

#### Native independent cases

Declare a typed schema and ordered named cases in one header:

```sql
TEST (
  name "order_status_maps_source_states",
  parameters (
    source_status string,
    expected_status string,
  ),
  cases (
    completed (source_status "completed", expected_status "completed"),
    cancelled (source_status "cancelled", expected_status "excluded"),
    pending (source_status "pending", expected_status "open"),
  ),
);

WITH
__source__raw__orders AS (
  SELECT 1 AS id, @param("source_status") AS status
),
__expected__stg_orders AS (
  SELECT 1 AS id, @param("expected_status") AS status
)
SELECT 1
```

The cases report independently as `order status: maps source states [completed]`, `[cancelled]`,
and `[pending]`. Authored order controls display order. Selection remains at the parent test's
resolved model or resource, so selecting `stg_orders` selects every case; there is no case selector.

Supported scalar types are `string`, `integer`, `boolean`, `float`, and exact `decimal`. Decimal
values are quoted, such as `tax_rate "0.2000"`, so they never pass through binary float. Boolean
and integer remain distinct. Raw SQL and collection parameters are rejected.

Nullable parameters use an expanded declaration and are valid where SQL can infer the null type:

```sql
parameters (
  cancellation_reason (type string, nullable true),
),
cases (
  completed (cancellation_reason null),
)
```

Every case provides exactly the declared parameters, and every declaration must appear as
`@param("name")` in the template. SQLBuild rejects missing, extra, incompatible, undeclared, and
unused values before execution.

Expansion is deterministic:

```text
parse TEST template and cases
  -> render typed @param values with the active adapter
  -> expand @const and @enum references
  -> expand macros
  -> validate SQL and compile expected models/assertions
```

Values can therefore feed macro arguments, for example
`@order_fixture(@param("source_status"))`. Parameters work in model, macro, UDF, and table-function
modes and preserve every expected model in multi-model tests.

Text and JSON output include parent/case identity and safe typed values. Compile JSON, manifests,
DAG checks, and compiled/runtime SQL artifacts retain source, block, case, and content-fingerprint
provenance. Changing one case changes that case's fingerprint without reassigning another case's
stable identity.

Scenarios are intentionally not parameterized. Keep one scenario per coherent business world so
capture and replay identity remains explicit.

#### Aggregate SQL case tables

When independent status is unnecessary, a normal SQL case table remains concise:

```sql
WITH cases(case_name, source_status, expected_status) AS (
  VALUES
    ('completed', 'completed', 'completed'),
    ('cancelled', 'cancelled', 'excluded')
),
__expected__status_mapping AS (
  SELECT case_name, expected_status FROM cases
)
SELECT 1
```

This produces one aggregate test result. Use native cases when each row must pass or fail
independently.

### Test placement

Place unit test files under `tests/unit/` in your project directory. SQLBuild discovers all `.sql` files in this directory recursively.

```
tests/
  unit/
    test_stg_orders.sql              # model test
    test_fact_orders.sql              # model test with assertion
    test_daily_revenue_chain.sql      # multi-model test
    test_line_total_cents_macro.sql   # macro test
    test_is_completed_order_udf.sql   # UDF test
    test_customer_orders_table_fn.sql # table function test
  scenarios/
    ...
```

### Running tests

Tests run automatically during `sqb build` in DAG order, before their target model is materialized.

Run tests standalone:

```bash
sqb test
```

Scope to specific models:

```bash
sqb test --select stg_orders
```

## Scenarios

Source: `concepts/scenarios.mdx`

End-to-end tests that build real project graphs against coherent fixture data.

Scenarios are end-to-end tests for coherent slices of your warehouse. You define fixture inputs, SQLBuild builds the real project graph against them in isolated physical relations, and you assert that the result is correct.

### When to use scenarios vs unit tests

[SQL unit tests](/concepts/testing) compile to a single comparison query. They are fast, inline, and work well for checking individual model transformations. But when you need to test across many models with related entities - customers that have orders, orders that have payments, refunds that reference original orders - a single query can become unwieldy or hit SQL size limits.

Scenarios materialize physical relations in the warehouse and build the actual model graph. This means:

- Fixture inputs are real tables, not CTEs inside one query
- Models execute with real SQL, real materializations, and real dependency ordering
- You can test end-to-end business logic across an entire pipeline slice
- Debugging is easier because you can inspect intermediate tables with `--retain`

Use unit tests for transformation logic. Use scenarios for coherent end-to-end validation.

### Authoring scenarios

Scenario files live under `tests/scenarios/` and use one file per scenario:

```
tests/
  scenarios/
    revenue/
      daily_revenue_minimal.sql
      daily_revenue_multi_order.sql
    fulfillment/
      fulfillment__late_shipment.sql
```

Folders are organizational only. The scenario name is the filename stem and must be globally unique across all discovered scenario files.

#### Scenario format

Each file has a `SCENARIO()` header followed by CTEs that define inputs, expected outputs, and assertions:

```sql
SCENARIO (
  description "Daily revenue includes only successful payments",
  tags ["revenue", "example"]
);

WITH
__ref__stg_orders AS (
  SELECT
    1 AS order_id, 10 AS customer_id, 1 AS waffle_type_id,
    2 AS quantity, CAST('2026-04-01 09:15:00' AS TIMESTAMP) AS ordered_at,
    'completed' AS status
),

__ref__stg_payments AS (
  SELECT
    1 AS payment_id, 1 AS order_id, 1700 AS amount_cents,
    'credit_card' AS payment_method,
    CAST('2026-04-01 09:16:00' AS TIMESTAMP) AS paid_at,
    'success' AS payment_status
  UNION ALL
  SELECT
    2 AS payment_id, 2 AS order_id, 1050 AS amount_cents,
    'credit_card' AS payment_method,
    CAST('2026-04-01 10:01:00' AS TIMESTAMP) AS paid_at,
    'failed' AS payment_status
),

__expected__daily_revenue AS (
  SELECT
    CAST('2026-04-01' AS DATE) AS revenue_date,
    1 AS order_count, 2 AS waffles_sold,
    1700 AS total_revenue_cents
),

__assert__all_orders_have_payments AS (
  SELECT *
  FROM __ref("fact_orders")
  WHERE payment_amount_cents IS NULL
)

SELECT 1
```

#### CTE conventions

| Prefix | Purpose |
|--------|---------|
| `__source__<name>` | Fixture source input. Materializes as a scenario table. |
| `__ref__<model>` | Fixture model boundary. Prevents SQLBuild from building that model upstream. |
| `__seed__<seed>` | Fixture seed data. |
| `__expected__<model>` | Full expected output. Compared order-insensitively against the scenario-built model. |
| `__assert__<name>` | Zero-row assertion. Passes if the query returns no rows; fails with the returned rows as diagnostics. |

For sources with two-part identity, use double underscores: `__source__raw__orders`.

Every scenario must have at least one fixture CTE and at least one `__expected__` or `__assert__` CTE.

Scenario SQL uses macros, enums, and constants available from the scenario file's directory under
`tests/scenarios/`. Public enums and constants available to a model are also available when the
scenario defines `__expected__model_name` output for that model. Model-private values and macros
available only to the model are not included. See
[How Visibility Works](/concepts/declaration-scopes/visibility#tests-and-expected-output).

#### SCENARIO() header

The header is metadata only:

| Field | Description |
|-------|-------------|
| `description` | Optional description string |
| `tags` | Optional list of string tags |

### How scenarios execute

#### Graph inference

SQLBuild infers which models to build from your scenario:

1. Target models come from `__expected__<model>` CTE names and `__ref(...)` calls inside `__assert__` CTEs
2. SQLBuild walks upstream from targets, building every required model
3. `__ref__<model>` fixtures act as boundaries - upstream traversal stops there
4. All required sources must be provided by `__source__` fixtures
5. Required project seeds are loaded automatically unless overridden by `__seed__` fixtures

#### Isolation

Scenario artifacts are physically isolated from production:

- Every scenario-owned relation uses a deterministic prefixed name (based on a hash of the project and scenario identity)
- All `ref()`, `source()`, and `seed()` calls resolve to scenario-owned relations, never production tables
- Fixture CTEs can read from existing warehouse relations if you choose, but downstream models always read the materialized scenario fixture, not the original

#### Execution flow

1. Clean any existing scenario artifacts from a previous run
2. Materialize source, ref, and seed fixtures as physical tables
3. Load required project seeds
4. Build required models in dependency order (incremental models run as full-refresh in scenarios)
5. Run expected-output comparisons (order-insensitive)
6. Run zero-row assertions
7. Clean up all scenario-owned artifacts (unless `--retain`)

#### Inspecting with `--retain`

When a scenario fails or you want to inspect intermediate state:

```bash
sqb scenario test --select daily_revenue_minimal --retain
```

This keeps all scenario-owned relations in the warehouse and prints a relation map showing the logical-to-physical name mapping. You can then query the scenario tables directly to debug.

Runtime artifacts (fixture SQL, model lifecycle SQL, check SQL, cleanup SQL) are always written to `target/run/scenarios/<scenario_name>/` regardless of `--retain`.

### Local scenario testing

Scenarios can run locally against DuckDB using captured JSONL snapshots - no warehouse connection needed. This is useful for CI pipelines and fast developer iteration.

#### Capture

First, capture scenario inputs from the real warehouse:

```bash
sqb scenario capture --select daily_revenue_minimal
```

This:

1. Materializes scenario input fixtures in the warehouse
2. Runs a preflight `COUNT(*)` on each fixture to check row counts against safety limits
3. Inspects column types and maps them to DuckDB-compatible types
4. Downloads rows as JSONL files (enforcing byte limits during writing)
5. Writes a `scenario.json` manifest with column metadata, types, row counts, and an input fingerprint
6. Cleans up warehouse artifacts

Snapshots are written to `tests/_scenario_snapshots/<scenario_name>/` and can be committed to version control. JSONL is human-readable and git-diffable.

#### Capture safety limits

Capture enforces row and byte limits to prevent accidentally saving large datasets. Limits can be set in `sqlbuild_project.toml`:

```toml
[scenario.snapshot_limits]
max_rows_per_relation = 10000
max_total_rows = 50000
max_bytes_per_relation = 10485760   # 10 MB
max_total_bytes = 52428800          # 50 MB
```

Or per-command via CLI flags:

```bash
sqb scenario capture --max-snapshot-rows 5000 --max-snapshot-total-rows 20000
sqb scenario capture --max-snapshot-bytes 5242880
```

CLI flags override TOML config. Use `--force` to bypass all limits:

```bash
sqb scenario capture --force
```

When a limit is exceeded, capture fails with a clear error and suggests narrowing the fixture query, raising the limit, or using `--force`.

#### Local replay

Run scenarios locally against DuckDB:

```bash
sqb scenario test --local
```

This:

1. Checks snapshot freshness via the input fingerprint (missing/stale snapshots are skipped by default)
2. Creates a temporary DuckDB database at `target/run/scenarios/<scenario_name>/local.duckdb`
3. Loads JSONL snapshots into typed DuckDB tables using column metadata from `scenario.json`
4. Transpiles model and check SQL from the project adapter dialect to DuckDB
5. Builds functions, models, and runs expected/assertion checks in DuckDB
6. Keeps the local DuckDB file for inspection (it lives under `target/`, so it's always retained)

#### Sync snapshots

Instead of running capture and test separately, sync snapshots in one command:

```bash
# Capture missing/stale snapshots, then run locally
sqb scenario test --local --sync-snapshots

# Recapture all snapshots, then run locally
sqb scenario test --local --refresh
```

With `--sync-snapshots`, fresh snapshots are reused. With `--refresh`, all selected snapshots are recaptured even if fresh.

#### Strict mode

By default, missing or stale snapshots are skipped with a warning. Use `--strict` to treat them as errors:

```bash
sqb scenario test --local --strict
```

#### Local type overrides

When the automatic warehouse-to-DuckDB type conversion produces an incompatible type, you can override it in `sqlbuild_project.toml`:

```toml
[scenario.local_type_overrides.snowflake]
"OBJECT" = "JSON"
"ARRAY" = "JSON"
"NUMBER(*,0)" = "BIGINT"
```

Override keys are structural type patterns. Values can reference matched type arguments with `{1}`, `{2}`, etc:

```toml
[scenario.local_type_overrides.bigquery]
"NUMERIC({1},{2})" = "DECIMAL({1},{2})"
```

These overrides are written into `scenario.json` during capture and used when loading snapshots into DuckDB.

### Cleanup

By default, remote scenario artifacts are dropped after each run (pass or fail). The janitor command also recognizes scenario artifacts and can clean retained or orphaned scenario relations:

```bash
sqb janitor
```

See the [CLI reference](/cli/scenario) for full command documentation.

### Limitations

- Custom materializations are not supported in scenarios yet. Scenario models using custom materializations will fail with a clear error.
- Local replay transpiles SQL from the project adapter dialect to DuckDB. Adapter-specific SQL that cannot be translated will produce a clear error with the failing resource name and reason.

## Selectors

Source: `concepts/selectors.mdx`

Target specific models, paths, tags, or DAG subsets with select and exclude flags.

Selectors let you scope commands to specific subsets of your project. They work with `plan`, `build`, `test`, `audit`, `seed`, `clone`, and `diff`.

### Basic usage

```bash
sqb build --select daily_revenue
sqb build --select daily_revenue customer_status_snapshot
sqb build --exclude stg_customers
```

`--select` (or `-s` for short) accepts one or more names. Multiple values are unioned. Space-separated names within one `--select` are also unioned. `--exclude` subtracts from the selected set.

When no `--select` is provided, all models are selected.

### Selector types

#### Name

Select a single model by name:

```bash
sqb build --select fact_orders
```

#### Tag

Select all models with a specific tag:

```bash
sqb build --select tag:staging
sqb build --select tag:acceptance
```

#### Path

Select all models under a directory path:

```bash
sqb build --select path:models/marts
sqb build --select models/marts
sqb build --select path:models/intermediate
```

Any name containing `/` is treated as a path selector, so `path:models/marts` and a bare `models/marts` work the same way. Path selectors require an explicit root directory: `models/`, `tasks/`, `assets/`, `checks/`, or `loaders/`. Nested paths work too: `models/staging/orders`.

#### Seed and source

```bash
sqb build --select seed:waffle_types
sqb build --select source:raw__orders
```

### Graph expansion

#### Upstream

Select a model plus all its upstream dependencies:

```bash
sqb build --select +daily_activity_rollup
```

#### Downstream

Select a model plus all its downstream dependents:

```bash
sqb build --select fact_orders+
```

#### Bidirectional

```bash
sqb build --select +fact_orders+
```

Graph expansion works with all selector types:

```bash
sqb build --select +tag:marts
sqb build --select path:models/staging+
```

### Path-between selectors

Select all models on the shortest path between two nodes:

```bash
sqb build --select fact_orders~daily_activity_rollup
```

With endpoint expansion:

```bash
sqb build --select +fact_orders~daily_activity_rollup+
```

This selects:
- All upstreams of `fact_orders`
- Every model on the path between `fact_orders` and `daily_activity_rollup`
- All downstreams of `daily_activity_rollup`

This is useful for rebuilding a specific slice of the DAG without manually listing every model in between.

### Intersection

Use commas to intersect selector results:

```bash
sqb build --select "tag:staging,path:models/finance"
```

This selects only models that match *both* conditions - in this case, models tagged `staging` that are also under the `models/finance` directory.

### Combining select and exclude

```bash
# Build all marts except daily_revenue
sqb build --select path:models/marts --exclude daily_revenue

# Build everything upstream of fact_orders, excluding staging models
sqb build --select +fact_orders --exclude tag:staging
```

### Error handling

Unknown model names, empty paths, and malformed selectors produce clear error messages:

```
unknown selector name 'nonexistent_model'
no models found under path 'models/nonexistent'.
no models found with tag 'nonexistent_tag'
path selector 'fact_orders~' requires names on both sides of '~'
```

If a path selector omits the root directory, SQLBuild asks for the explicit form:

```
path selectors require an explicit root: use 'models/', 'tasks/', 'assets/', 'checks/', or 'loaders/'
```

## Column Lineage

Source: `concepts/column-lineage.mdx`

Trace individual columns through your SQL pipeline - understand where data comes from and where it goes.

### Why column lineage matters

**Impact analysis** - Before changing a source column, see exactly which downstream models and columns are affected. A rename or type change in `raw__orders.id` can be traced through every model that consumes it, even indirectly.

**Debugging data issues** - When a column has unexpected values, trace it upstream to find where the data originates and what transformations it passes through. Instead of reading SQL files and mentally joining dependencies, ask SQLBuild to show the path.

**Documentation** - Column lineage provides machine-readable metadata about your pipeline. The JSON output can feed data catalogs, governance tools, or custom dashboards.

### How it works

SQLBuild analyzes column lineage statically at compile time. No warehouse connection is needed. The analyzer parses each model's SQL, resolves `ref()` and `source()` calls, and traces columns through `SELECT` lists, CTEs, JOINs, subqueries, and expressions.

Column lineage requires SQL analysis to be enabled in project settings (it is by default).

### Transform types

Each lineage edge is classified by how the column is transformed:

| Transform | Description | Example |
|-----------|-------------|---------|
| `direct` | Column passes through unchanged | `SELECT order_id FROM ...` |
| `cast` | Column is explicitly cast to a different type | `SELECT CAST(id AS BIGINT)` |
| `expression` | Column is used in a computed expression | `SELECT amount * 100 AS amount_cents` |
| `aggregation` | Column is used inside an aggregate function | `SELECT SUM(amount) AS total` |
| `star` | Column is included via `SELECT *` | `SELECT * FROM ...` |
| `constant` | Output column is a literal value with no upstream dependency | `SELECT 'active' AS status` |

Transform classification helps you understand the nature of each dependency. A `direct` edge means the column is a simple passthrough - safe to rename if you rename the source. An `expression` or `aggregation` edge means the column is computed - the upstream value is an input to a calculation, not a 1:1 mapping.

### Confidence levels

Each edge also carries a confidence level indicating how certain the analyzer is about the traced dependency:

| Confidence | Meaning |
|------------|---------|
| `high` | The lineage path is fully resolved through known SQL constructs |
| `medium` | The path is likely correct but involves constructs the analyzer handles with heuristics |
| `low` | The path is best-effort - complex SQL patterns or unsupported constructs may reduce accuracy |

### Analysis modes

Column lineage supports two analysis modes that trade off speed against depth of analysis.

**Rich mode** uses the SQL analysis optimizer to resolve columns through CTEs, subqueries, and multi-level nesting with full transform classification. Thorough, but slower because the optimizer runs per column per model.

**Fast mode** parses the SQL AST directly to extract column mappings, resolve CTE references, and classify transforms. It handles the same SQL patterns that most column lineage tools support and is fast enough to run on every compile.

`sqb compile` defaults to fast mode because it runs frequently and analyzes the entire project. `sqb lineage` defaults to rich mode because it targets a specific column in a scoped slice of the DAG, where the deeper analysis is worth the cost. Both are overridable:

```bash
sqb compile --lineage-mode rich
sqb lineage fact_orders.payment_amount_cents --mode fast
```

### Using column lineage

#### Interactive tracing with `sqb lineage`

The target syntax is `model_name.column_name`. Trace a column upstream to see where its values come from:

```bash
sqb lineage daily_revenue.total_revenue_cents
```

```
Column trace  daily_revenue.total_revenue_cents  upstream

└── stg_payments.amount_cents (aggregation)
    └── raw__payments.amount_cents (direct)
```

Each hop is annotated with how the value was derived. Here `total_revenue_cents` is an aggregation of `stg_payments.amount_cents`, which is a direct passthrough from the source.

Use `--direction downstream` to trace the other way - every column derived from this one:

```bash
sqb lineage stg_payments.amount_cents --direction downstream
```

```
Column trace  stg_payments.amount_cents  downstream

├── daily_revenue.avg_order_value_cents (aggregation)
├── daily_revenue.total_revenue_cents (aggregation)
├── daily_revenue.total_revenue_dollars (aggregation)
├── dim_customers.lifetime_spend_cents (aggregation)
└── fact_orders.payment_amount_cents (direct)
```

Column lineage supports `upstream` (default) and `downstream` directions (not `both` - model lineage supports `both`).

#### Model lineage

`sqb lineage` also traces model-level dependencies when the target has no column (no dot):

```bash
sqb lineage fact_orders
```

```
Lineage  model  fact_orders  models/marts/fact_orders.sql  upstream

├── model  stg_orders  models/staging/stg_orders.sql
│   └── source  raw__orders  sources/raw.yml
├── model  stg_payments  models/staging/stg_payments.sql
│   └── source  raw__payments  sources/raw.yml
├── seed  waffle_types  seeds/waffle_types.csv
└── udf  udf__is_completed_order
```

Each node is tagged with its resource type (`model`, `source`, `seed`, `udf`) and file path. Use `--direction both` to show upstream and downstream together:

```bash
sqb lineage daily_revenue --direction both
```

```
Lineage  model  daily_revenue  models/marts/daily_revenue.sql  both

upstream
├── model  stg_orders  models/staging/stg_orders.sql
│   └── source  raw__orders  sources/raw.yml
└── model  stg_payments  models/staging/stg_payments.sql
    └── source  raw__payments  sources/raw.yml
downstream
```

#### Options

| Flag            | Description                                                                       |
| --------------- | --------------------------------------------------------------------------------- |
| `--direction`   | `upstream` (default), `downstream`, or `both`. `both` is model lineage only.      |
| `--depth`       | How many hops to traverse: an integer or `all` (default `all`).                   |
| `--format`      | `tree` (default), `list` (an edge list of `a -> b` pairs), or `json`.             |
| `--mode`        | Column lineage mode: `rich` (default) or `fast`.                                  |

See the [lineage CLI reference](/cli/lineage) for full flag documentation and output format examples.

#### Batch analysis with `sqb compile`

Every compile run computes column lineage for analysis and reports a summary:

```bash
# Default: fast column lineage
sqb compile

# Skip column lineage
sqb compile --lineage-mode none

# JSON report includes per-model lineage summary
sqb compile --json
```

In the JSON compile report, each model includes a `lineage` field with `column_count`, `edge_count`, and `has_star` metadata. It does not contain the full edge graph; use `sqb lineage <model>[.<column>] --format json` when you need structured lineage details.

See the [compile CLI reference](/cli/compile) for details on the compile report format.

#### Integration with contract validation

Column lineage feeds into compile-time contract validation. When a model declares columns in its `MODEL()` header, the compiler uses inferred column information to check that:

- Every declared column exists in the query output
- Column types match the declared types (when `type_enforcement` is enabled)

These checks run automatically during `sqb compile` and report diagnostics with source-annotated error messages.

### Limitations

- Column lineage requires SQL analysis to be enabled (`sql_analysis = true` in settings, which is the default)
- Complex SQL patterns (deeply nested correlated subqueries, dynamic SQL, adapter-specific functions) may reduce accuracy or confidence
- `SELECT *` is tracked as a `star` transform - the analyzer knows the column passes through but the mapping is less precise than explicit column references
- Column lineage is computed statically from SQL text. Runtime-only column additions (e.g. from dynamic UDFs) are not tracked

## Data Diffs

Source: `concepts/diff.mdx`

Compare schemas and data between targets or virtual environments to validate changes before promotion.

SQLBuild can compare schemas and row-level data between two build contexts. This lets you validate that changes produce the expected results before promoting them.

`sqb diff FROM:TO` compares:

- **two targets** (e.g. `prod:dev`) in direct mode, or
- **two virtual environments** (VDEs) when [virtual environments](/concepts/virtual-environments) are enabled.

The mechanics below are identical for both; only what `FROM` and `TO` refer to changes.

In direct mode, each name resolves a configured target, including its named connection and
authoritative database/schema namespace. Unknown connection references fail during offline
configuration loading before SQLBuild attempts the comparison.

```bash
sqb diff prod:dev --full --select customer_status_snapshot
```

### Comparison modes

Every diff requires exactly one mode:

#### Full diff

Compares both schema and row-level data for the selected models:

```bash
sqb diff prod:dev --full --select fact_orders
```

Rows are joined on the model's `unique_key` and compared column by column. The output shows:
- Row counts for each side
- How many rows are equal, unequal, or only in one side
- Which columns have mismatches with match percentages
- Example values showing what changed

#### Schema-only diff

Compares column names and types without looking at row data:

```bash
sqb diff prod:dev --schema-only --select fact_orders
```

Useful for quick structural checks or when row comparison would be too expensive.

#### Bounded diff

Compares only a recent window of data using the model's cursor:

```bash
sqb diff prod:dev --bounded 14d --select hourly_order_activity
```

For timestamp cursors, the bound is a duration (`14d`, `6h`, `30m`). For integer cursors, the bound is an integer value. If the model has no cursor configured, the diff falls back to a full row comparison.

### Row matching

Rows are matched between the two sides using the model's `unique_key`. Models without a `unique_key` can use schema-only diff but cannot run full or bounded row comparisons.

The diff output categorises rows as:
- **Equal** - same key, same values on both sides
- **Unequal** - same key, different values (with per-column breakdown)
- **Left only** - exists in the FROM side but not TO
- **Right only** - exists in the TO side but not FROM

### Tolerances

Numeric columns can have tolerance rules to avoid false positives from floating-point differences or acceptable variance. Configure tolerances in the model's `MODEL()` header:

```sql
MODEL (
  materialized incremental,
  ...
  row_diff_tolerances (
    by_column (
      total_revenue_cents (
        absolute 1,
      ),
    ),
  ),
);
```

Tolerance rules support:
- **`absolute`** - maximum allowed absolute difference (e.g. `1` means values differing by 1 or less are treated as equal)
- **`relative`** - maximum allowed relative difference as a decimal (e.g. `0.01` for 1%)

Tolerances can be set per-column (`by_column`) or per-type (`by_type`).

### Excluded columns

Columns that are expected to differ between the two sides (like timestamps or context-specific values) can be excluded from the row comparison:

```sql
MODEL (
  materialized incremental,
  ...
  row_diff_exclude_columns [latest_order_status],
);
```

Excluded columns are still shown in the schema comparison but skipped during row-level diffing. A column cannot be in both `row_diff_exclude_columns` and `unique_key`.

### Verbose output

Add `--verbose` or `-v` to see more example rows for mismatches and side-only rows:

```bash
sqb diff prod:dev --full --select customer_status_snapshot --verbose
```

Default sample limits are 3 per category. Verbose mode increases this to 10. You can also set exact limits:

```bash
sqb diff prod:dev --full --select customer_status_snapshot --max-column-examples 20 --max-row-only-examples 5
```

### Selectors

Diff requires `--select` in the current version. You can use any selector syntax:

```bash
# Diff a single model
sqb diff prod:dev --full --select customer_status_snapshot

# Diff all models in a path
sqb diff prod:dev --schema-only --select path:models/marts

# Diff models with a specific tag
sqb diff prod:dev --full --select tag:acceptance
```

### Exit codes

`sqb diff` returns exit code `0` when all selected models have no differences, and `1` when any model has schema or row differences. This makes it usable in CI pipelines as a validation gate.

## Overview

Source: `concepts/declaration-scopes.mdx`

Limit enums, constants, and macros to the parts of a project that use them.

Most projects can keep enums, constants, and macros in their ordinary top-level directories. Those
declarations are available throughout the project.

When an enum, constant, or macro should be available only within one folder or its child folders,
you can keep it near the SQL that uses it. SQLBuild uses the declaration directory's location to
decide which files can access it. No TOML configuration is required.

| Where the declaration lives | Who can use it |
|-------------------------------------|--------------------|
| Top-level `macros/`, `constants/`, or `enums/` | The whole project |
| Nested `macros/`, `constants/`, or `enums/` | Files in that folder and folders below it |
| Nested `_macros/`, `_constants/`, or `_enums/` | Files directly in that folder only |
| An underscored constant or enum inside `MODEL()` | That model and its inline SQL hooks only |

Macro declarations are Python files (`.py`). Constant and enum declarations are SQL files
(`.sql`).

### Example

The annotation beside each directory shows where its contents are available:

```text
models/
├── constants/                 published throughout models/
│   └── warehouse.sql
└── commerce/
    ├── macros/                published throughout commerce/
    │   └── currency.py
    ├── _enums/                exact commerce/ directory only
    │   └── grain.sql
    ├── orders.sql              sees warehouse, currency, and grain
    ├── finance/
    │   ├── macros/            published throughout finance/
    │   │   └── tax.py
    │   └── revenue.sql         sees warehouse, currency, and tax
    └── fulfillment/
        └── shipments.sql       sees warehouse and currency
```

A nested unprefixed role applies to its folder and everything below it. An underscored role applies
only to files directly beside it. The same unprefixed role name applies to the whole project only
when it is at the project root.

| Resource | Visible from the example tree | Not visible |
|----------|-------------------------------|-------------|
| `orders.sql` | Warehouse constant, commerce macro, commerce-folder-only enum | Finance macro |
| `finance/revenue.sql` | Warehouse constant, commerce macro, finance macro | Commerce-folder-only enum |
| `fulfillment/shipments.sql` | Warehouse constant, commerce macro | Commerce-folder-only enum, finance macro |

Declarations do not flow upward or sideways into sibling directories.

### Terms used in text output

The CLI's text output uses short labels for the same four rules:

| Canonical label | Plain-language meaning |
|-----------------|------------------------|
| `project` | Available throughout the project |
| `descendant-public` | Available in this folder and folders below it |
| `exact-owner-private` | Available directly in this folder only |
| `model-private` | Available to one model only |

Here, an **owner folder** is simply the folder directly containing a model, test, hook, function, or
other authored resource. The [Scope Explorer](/concepts/declaration-scopes/explorer) shows the owner
folder, its parents, and project-wide declarations separately.

JSON keeps the underlying enum values for integrations. Its `scope` field uses `global`,
`inherited`, `local`, or `private`, while derived `visibility` values use underscores, such as
`descendant_public` and `exact_owner_private`. Consumers should use the fields documented in the
versioned JSON schema rather than parsing text labels.

### Choose a location

| Where the value is needed | Placement |
|---------------------------|-----------|
| One model only | In that model's `MODEL()` header |
| Files directly in one folder | In an underscored role beside those files |
| Files across one folder tree | In an unprefixed role at their nearest shared parent folder |
| Different resource trees, such as models and tests | In a top-level declaration role |

SQLBuild computes the lowest common owner of every declaration's runtime consumers. A project-wide
declaration is valid only when no narrower supported owner contains all consumers. This keeps the
top-level roles as a genuine project API instead of a neutral dumping ground.

### Explore the feature

    See which declarations a model, test, hook, or function can use.
    Choose the narrowest folder that contains every real use.
    Ask SQLBuild what a file can use and preview how moving it would change that answer.

Learn the features themselves in [Enums](/concepts/enums), [Constants](/concepts/constants), and
[Writing Macros](/concepts/macros). See [Interpolation](/concepts/interpolation) for project,
environment, and runtime context values, which are separate from declarations.

## How Visibility Works

Source: `concepts/declaration-scopes/visibility.mdx`

See which enums, constants, and macros are available to each SQL file.

For most SQL, the rule is simple:

> A file can use declarations available to the whole project, declarations in unprefixed role
> folders beside or above it, and declarations in an underscored role folder directly beside it.

### Start from the SQL file

SQLBuild starts from the file containing the SQL and walks up that file's directory tree. The folder
directly containing the file is its **owner folder**.

```text
models/
├── constants/                 available throughout models/
│   └── warehouse.sql
└── commerce/
    ├── enums/                 available throughout commerce/
    │   └── order_status.sql
    ├── _constants/       available directly in commerce/ only
    │   └── minimum_value.sql
    ├── orders.sql
    └── history/
        └── archived_orders.sql
```

From this tree:

| File | Can use |
|------|---------|
| `orders.sql` | `warehouse`, `order_status`, and `minimum_value` |
| `history/archived_orders.sql` | `warehouse` and `order_status` |

`minimum_value` is not available in `history/` because `_constants/` applies only to files
directly beside it.

### Supported resource trees

Scoped declaration directories can be placed below these SQL resource roots:

| Root | Contents |
|------|----------|
| `models/` | Models and inline model hooks |
| `tests/unit/` | Unit tests |
| `tests/scenarios/` | Scenarios |
| `hooks/sql/` | Named SQL hooks |
| `functions/sql/` | SQL functions |
| `audits/` | Audits |
| `sources/` | Inline source expressions |

Each root is a separate tree. For example, `models/constants/` does not make declarations available
under `tests/`. Put a declaration in the top-level `constants/`, `enums/`, or `macros/` directory
when it must be available across different resource trees. Project-root `_constants/`, `_enums/`,
and `_macros/` directories are invalid because there is no owner folder at the project root for
them to be private to.

### Which file controls visibility?

| SQL being compiled | SQLBuild starts from |
|--------------------|----------------------|
| Model query | The model file |
| Inline SQL hook in a model | The model file |
| Unit test or scenario SQL | The test or scenario file |
| Named SQL hook | The hook file under `hooks/sql/` |
| SQL function | The function file under `functions/sql/` |
| Audit | The audit file |
| Inline source expression | The source definition |

This means a reusable named hook does not change meaning depending on which model calls it. The
hook uses declarations available where the hook itself is stored.

### Tests and expected output

A test first sees declarations available from its own folder tree. It may also use file-based enums
and constants available to a model for which it defines expected output.

```sql
TEST();

WITH
__expected__orders AS (
  SELECT
    1 AS order_id,
    @enum("order_status").COMPLETED AS status
)
SELECT 1
```

Because the test defines `__expected__orders`, the test may use file-based enums and constants
available to `orders`, including declarations in exact-folder `_enums/` and `_constants/` roles.
Scope Explorer describes this as **available through expected output for model `orders`**. This is
an additional relationship, not another visibility level.

This additional access does **not** include:

- Macros available only to the model
- Enums or constants declared privately inside the model's `MODEL()` header
- Declarations from a model merely mentioned by filename or directory layout

Only an explicit `__expected__model_name` section adds the model's eligible file-based enums and
constants. When a test checks several models, SQLBuild combines the declarations available through
all expected models and makes that deterministic union available while compiling the entire test.

### Macros importing macros

A macro file may import another project macro file when the imported macro is available from the
importing file's location. The same directory rules apply as they do to SQL.

```python
# models/commerce/macros/orders.py
from macros.currency import round_money

def formatted_total(expression: str) -> str:
    return round_money(expression)
```

A broadly available macro cannot import a macro from a narrower child or sibling directory. See
[Composition and Context](/concepts/macros/composition-and-context) for complete examples.

### Names do not shadow

Public names must be unique within their feature:

- One public macro name cannot be defined twice.
- One public enum name cannot be defined twice.
- One public constant name cannot be defined twice.

Moving a declaration into a narrower directory changes where it is available; it does not create a
second version that overrides another declaration.

Macros, enums, and constants use separate namespaces, so these three references may coexist:

```sql
@format_currency()
@const("format_currency")
@enum("format_currency").USD
```

  Choose the simplest directory that matches where a declaration is used.

## Where to Put Declarations

Source: `concepts/declaration-scopes/placement.mdx`

Choose the narrowest folder that contains every real use.

Start with the ordinary project-wide directories unless you have a reason to limit access:

```text
macros/
enums/
constants/
```

Move a declaration closer to its users when it should be available only in one folder or one folder
tree.

### Choose a location

| Where it is needed | Location |
|--------------------|----------|
| One model only | Inside that model's `MODEL()` header, for enums and constants |
| SQL files directly in one directory | `_macros/`, `_enums/`, or `_constants/` |
| A directory and its descendants | `macros/`, `enums/`, or `constants/` |
| Different trees, such as models and tests | Top-level `macros/`, `enums/`, or `constants/` |

### One directory

These two models use the same constant and both sit directly in `commerce/`:

```text
models/
└── commerce/
    ├── _constants/
    │   └── minimum_value.sql
    ├── orders.sql
    └── customers.sql
```

Use `_constants/` because no descendant directory needs the value.

### One directory tree

These models use the same constant across two child directories:

```text
models/
└── commerce/
    ├── constants/
    │   └── reporting_day.sql
    ├── finance/
    │   └── revenue.sql
    └── fulfillment/
        └── shipments.sql
```

Use `constants/` in `commerce/` so both child directories can use it.

### Different resource trees

When a declaration is used directly from unrelated trees, make it project-wide:

```text
my_project/
├── constants/
│   └── order_status.sql
├── models/
│   └── commerce/orders.sql
└── tests/
    └── scenarios/order_lifecycle.sql
```

Top-level placement is valid when consumers genuinely cross resource trees or otherwise have no
shared owner folder. SQLBuild applies the same nearest-shared-folder analysis to project-wide
declarations, so a declaration used only under one narrower folder must move closer to those users.

### What SQLBuild checks

Every declaration must be used by real compiled SQL. A name appearing only in a comment, quoted
string, mock identity, or documentation does not count as use.

For every declaration, including project-wide declarations, SQLBuild finds the nearest shared owner
folder of the files that use it. If the declaration is in a broader location, the error shows:

- Where the declaration is now
- Which files use it
- Which directory form is required
- The destination directory

These checks use the complete project rather than only the models selected by the current command.

  Use Scope Explorer to see what a file can access or preview moving the file.

## Scope Explorer

Source: `concepts/declaration-scopes/explorer.mdx`

Inspect visibility, explain resolution, browse declarations, and preview moves offline.

Scope Explorer answers questions about declaration visibility through `sqb scope`. It is read-only
and offline: it never connects to the warehouse, moves files, or edits configuration.

Use this page for common workflows. See the [`sqb scope` CLI reference](/cli/scope) for every flag,
filter, text section, and JSON field.

### Example project

The examples below use two domains with project-wide currency helpers:

```text
project/
├── macros/
│   └── currency.py                      add_tax, round_money
├── models/
│   ├── commerce/
│   │   ├── constants/limits.sql        minimum_order_value
│   │   ├── enums/status.sql            order_status
│   │   ├── macros/orders.py            formatted_order_total
│   │   ├── orders.sql
│   │   └── returns/returns.sql
│   └── finance/
│       ├── enums/status.sql            finance_status
│       ├── macros/margin.py            calculate_margin
│       ├── finance_summary.sql
│       └── reports/margin_report.sql
└── tests/
    └── unit/orders__completed_only.sql
```

`formatted_order_total` composes the project-wide functions through ordinary Python calls:

```python
from macros.currency import add_tax, round_money

def formatted_order_total(expression: str) -> str:
    return round_money(add_tax(expression))
```

`orders.sql` uses the commerce constant and macro. The returns model also uses all three commerce
declarations, so they are correctly published throughout that domain. The two finance models use
both finance declarations. This gives every scoped declaration a real consumer and valid placement.

### See available and used declarations

Start with a model, test, scenario, hook, function, audit, source, or authored resource path to
inspect its directory-derived scope. A declaration identity instead opens its explanation. This
excerpt of the main report sections puts actual usage beside the complete directory-derived scope:

```console
$ sqb scope model:orders
Scope
  Target: model:orders
  Resource: model:orders
  Path: models/commerce/orders.sql

Used (2)
  ├─ ● constant:minimum_order_value  [constant; descendant-public; inherited_ancestor; type integer; role models/commerce/constants]  models/commerce/constants/limits.sql:1:1
  └─ ● macro:formatted_order_total  [macro; descendant-public; inherited_ancestor; params 1; role models/commerce/macros]  models/commerce/macros/orders.py:4:1

Scope chain
  ├─ exact-owner-private models/commerce (3)
  ├─ descendant-public models (0)
  └─ project global (2)

Available (3 of 5, 2 collapsed)
  ├─ ● constant:minimum_order_value  [constant; descendant-public; inherited_ancestor; type integer; role models/commerce/constants]  models/commerce/constants/limits.sql:1:1
  ├─ ○ enum:order_status  [enum; descendant-public; inherited_ancestor; members 4; type VARCHAR; role models/commerce/enums]  models/commerce/enums/status.sql:1:1
  └─ ● macro:formatted_order_total  [macro; descendant-public; inherited_ancestor; params 1; role models/commerce/macros]  models/commerce/macros/orders.py:4:1
  … 2 globals collapsed; run sqb scope model:orders --globals all

Diagnostics (0)
  (none)
Completeness: complete
```

`●` marks a declaration included in `Used`: a direct usage by default, or a followed declaration
dependency when `--dependency-depth` is nonzero. `○` marks a declaration present in the section but
not in `Used`.

The compact labels translate to ordinary folder rules:

| Output label | Meaning in this report |
|--------------|------------------------|
| `project` | Available throughout the project |
| `descendant-public` | Available from a folder at or above this resource |
| `exact-owner-private` | Available directly in this resource's owner folder only |
| `inherited_ancestor` | Visible because an unprefixed role publishes it down the folder tree |
| `role models/commerce/macros` | The declaration role begins at this path |

In the scope chain, the first path is the resource's owner folder, followed by parent folders and
the project declaration roles. The counts show declarations defined at each path; the chain label
describes how SQLBuild reaches that path, not the visibility of every declaration counted there.
Unused project-wide declarations stay collapsed by default so a large project API does not hide the
owner-folder facts.

### Follow composed dependencies

`Used` is direct by default. Add `--dependency-depth` to follow declarations used by those
declarations. The expanded `Used` section is:

```console
$ sqb scope model:orders --used-only --dependency-depth 1
Used (4)
  ├─ ● constant:minimum_order_value  [constant; descendant-public; inherited_ancestor; type integer; role models/commerce/constants]  models/commerce/constants/limits.sql:1:1
  ├─ ● macro:add_tax  [macro; project; dependency; params 1; role macros]  macros/currency.py:1:1
  ├─ ● macro:formatted_order_total  [macro; descendant-public; inherited_ancestor; params 1; role models/commerce/macros]  models/commerce/macros/orders.py:4:1
  └─ ● macro:round_money  [macro; project; dependency; params 1; role macros]  macros/currency.py:5:1
```

SQLBuild derives these edges from actual Python calls, including nested calls and calls reached
through private helpers. Merely importing a macro does not make it used. Increase the depth to
follow longer chains.

Explain the composed macro to see its direct dependencies, consumers, and required placement. The
ordinary report appears first; its `Explanation` section is:

```console
$ sqb scope model:orders --explain macro:formatted_order_total
Explanation
  └─ ● macro:formatted_order_total  [macro; descendant-public; inherited_ancestor; params 1; role models/commerce/macros]  models/commerce/macros/orders.py:4:1
     Owner: (none)
     Owning path: models/commerce
     Consumers: model:orders, model:returns
     Dependencies: macro:add_tax, macro:round_money
     Grants: (none)
     Required scope: descendant-public
     Required path: models/commerce
     Promotion impact: (none)
```

#### Catch placement that is too broad

If `returns.sql` stopped using `formatted_order_total`, only `orders.sql` would consume it. The same
explanation would then show that descendant-public placement is broader than necessary:

```console
Explanation
  └─ ● macro:formatted_order_total  [macro; descendant-public; inherited_ancestor; params 1; role models/commerce/macros]  models/commerce/macros/orders.py:4:1
     Owner: (none)
     Owning path: models/commerce
     Consumers: model:orders
     Dependencies: macro:add_tax, macro:round_money
     Grants: (none)
     Required scope: exact-owner-private
     Required path: models/commerce
     Promotion impact: model:orders

Diagnostics (1)
  ERROR S008 models/commerce/macros/orders.py: Declaration 'macro:formatted_order_total' is currently descendant-public at 'models/commerce' (models/commerce/macros/orders.py); required exact-owner-private at 'models/commerce'. Consumers: model:orders. Move it to 'models/commerce/_macros/'
Completeness: complete
```

This is actionable placement guidance, not only a visibility lookup.

### Find declarations outside the scope

Nearby discovery is useful when you know a declaration exists but not why the current resource
cannot use it. The relevant section is:

```console
$ sqb scope model:orders --include-nearby
Nearby unavailable (2 of 2)
  ├─ ○ enum:finance_status  [enum; descendant-public; sibling_scope; members 3; type VARCHAR; role models/finance/enums]  models/finance/enums/status.sql:1:1
  └─ ○ macro:calculate_margin  [macro; descendant-public; sibling_scope; params 2; role models/finance/macros]  models/finance/macros/margin.py:4:1
```

The declarations are known, but they belong to a different folder branch. Here, the inspected
resource belongs to `models/commerce`, while the declarations belong to `models/finance`.
`sibling_scope` is the compact output label for that situation. Ask for one complete explanation
when you know a declaration's identity. After the ordinary report, the command adds:

```console
$ sqb scope model:orders --explain macro:calculate_margin
Explanation
  └─ ○ macro:calculate_margin  [macro; descendant-public; sibling_scope; params 2; role models/finance/macros]  models/finance/macros/margin.py:4:1
     Owner: (none)
     Owning path: models/finance
     Consumers: model:finance_summary, model:margin_report
     Dependencies: (none)
     Grants: (none)
     Required scope: descendant-public
     Required path: models/finance
     Promotion impact: (none)
```

An explanation distinguishes a known but inaccessible declaration from an unknown name. It also
shows whether the declaration is placed more broadly than its real consumers require.

### See declarations available through expected output

Tests and scenarios can use file-based enums and constants available to a model when they define
that model's expected output. This includes eligible exact-folder declarations, but not declarations
inside `MODEL()`. The access applies to the whole test or scenario and remains separate from
declarations visible through its own folder tree. The relevant report sections are:

```console
$ sqb scope test:orders__completed_only --used-only
Used (1)
  └─ ● enum:order_status  [enum; descendant-public; expected_model through model:orders; members 4; type VARCHAR; role models/commerce/enums]  models/commerce/enums/status.sql:1:1

Relationship grants (1 of 1)
  └─ ● enum:order_status  [enum; descendant-public; expected_model through model:orders; members 4; type VARCHAR; role models/commerce/enums]  models/commerce/enums/status.sql:1:1
```

The compact reason `expected_model through model:orders` means **available through expected output
for model `orders`**. With multiple expected models, SQLBuild combines their eligible file-based
enums and constants into one deterministic set for the test or scenario. These relationships do
not grant macros or declarations defined inside a model's `MODEL()` header.

### Preview a resource move

Use `--as-path` to see the scope delta before moving an existing model, test, hook, or function. The
ordinary report is followed by:

```console
$ sqb scope model:orders --as-path models/finance/orders.sql
Move preview
  Resource: model:orders
  Destination: models/finance/orders.sql
  Ownership root: models
  Retained (2)
    ├─ ○ macro:add_tax  [macro; project; global; params 1; role macros]  macros/currency.py:1:1
    └─ ○ macro:round_money  [macro; project; global; params 1; role macros]  macros/currency.py:5:1
  Gained (2)
    ├─ ○ enum:finance_status  [enum; descendant-public; inherited_ancestor; members 3; type VARCHAR; role models/finance/enums]  models/finance/enums/status.sql:1:1
    └─ ○ macro:calculate_margin  [macro; descendant-public; inherited_ancestor; params 2; role models/finance/macros]  models/finance/macros/margin.py:4:1
  Lost (3)
    ├─ ● constant:minimum_order_value  [constant; descendant-public; inherited_ancestor; type integer; role models/commerce/constants]  models/commerce/constants/limits.sql:1:1
    ├─ ○ enum:order_status  [enum; descendant-public; inherited_ancestor; members 4; type VARCHAR; role models/commerce/enums]  models/commerce/enums/status.sql:1:1
    └─ ● macro:formatted_order_total  [macro; descendant-public; inherited_ancestor; params 1; role models/commerce/macros]  models/commerce/macros/orders.py:4:1
  Private retained (0)
    (none)
  Relationship retained (0)
    (none)
  Invalidated usages (2)
    - constant:minimum_order_value
    - macro:formatted_order_total
```

The move would gain finance declarations and lose commerce declarations. More importantly,
`Invalidated usages` separates the losses that break the model from declarations that happened to
be available but were never used. The preview does not move or rewrite any file.

### Check a prospective path

Inspect visibility before a resource exists:

```console
$ sqb scope --at models/commerce/returns/new_return.sql
Scope
  Target: models/commerce/returns/new_return.sql
  Path: models/commerce/returns/new_return.sql
  Status: prospective

Used (0)
  (none)

Scope chain
  ├─ exact-owner-private models/commerce/returns (0)
  ├─ descendant-public models/commerce (3)
  ├─ descendant-public models (0)
  └─ project global (2)

Available (3 of 5, 2 collapsed)
  ├─ ○ constant:minimum_order_value  [constant; descendant-public; inherited_ancestor; type integer; role models/commerce/constants]  models/commerce/constants/limits.sql:1:1
  ├─ ○ enum:order_status  [enum; descendant-public; inherited_ancestor; members 4; type VARCHAR; role models/commerce/enums]  models/commerce/enums/status.sql:1:1
  └─ ○ macro:formatted_order_total  [macro; descendant-public; inherited_ancestor; params 1; role models/commerce/macros]  models/commerce/macros/orders.py:4:1
  … 2 globals collapsed; run sqb scope --at models/commerce/returns/new_return.sql --globals all

Relationship grants (0 of 0)
  (none)

Nearby unavailable (0 of 0)
  (none)

Diagnostics (1)
  ERROR S013 models/commerce/returns/new_return.sql: Runtime usage and relationship facts are unavailable for a prospective path
Completeness: partial
```

Visibility is available from the proposed path. Actual usage and expected-output relationships do
not exist yet, so the command preserves the useful static result while clearly marking it partial.

### Browse large declaration sets

In a larger project, browse returns folder summaries rather than an arbitrary prefix of the
declaration inventory. The `used` counts are direct usages by this target; browse does not apply
dependency-depth expansion:

```console
$ sqb scope model:orders --browse global
Scope folders
  Path: global

  ├─ constants/  146 declarations, 18 used, 4 children; constant 146
     sqb scope model:orders --browse global/constants
     sqb scope model:orders --list global/constants
  ├─ enums/  84 declarations, 11 used, 3 children; enum 84
     sqb scope model:orders --browse global/enums
     sqb scope model:orders --list global/enums
  └─ macros/  231 declarations, 27 used, 8 children; macro 231
     sqb scope model:orders --browse global/macros
     sqb scope model:orders --list global/macros

Diagnostics (0)
  (none)
Completeness: complete
```

Choose a bounded folder, then use `--list`. Definition-path, kind, glob, and actual-usage filters
can be combined, and paged sections use stable declaration identities as cursors.

### Automation

Use `--json` for editor integrations and repository tooling. Output has a versioned schema, stable
ordering, filters, pagination, and move-preview results. Constant values, credentials, and secret
connection settings are not included.

    Review the directory rules behind the report.
    See all selectors, filters, pagination options, output sections, and JSON behavior.

## Kata SQL Architecture Checks

Source: `concepts/kata.mdx`

Enforce opt-in SQL architecture and model-shape policy over your compiled project.

Kata is SQLBuild's opt-in SQL architecture policy. It compiles the project, then checks model
structure, naming, dependency boundaries, joins, contracts, and test coverage. Built-in checks run
offline: they do not execute warehouse SQL or rewrite source files. Findings have stable codes and
concrete remediations.

Kata is error-only: every retained finding blocks the command. Use it for conventions that a team
has deliberately adopted, not as a collection of advisory style warnings.

Tests codify behavioral expectations; Kata codifies architectural expectations for SQL models.
For equivalent boundaries, repository structure, and code-shape checks in Python projects, see
[Fensu](https://docs.fensu.dev/).

### Where Kata fits

| Command | Responsibility |
|---------|----------------|
| `sqb compile` | SQL validity, references, inferred columns, contracts, and lineage |
| `sqb lint` / `sqb format` | SQL presentation and formatting |
| `sqb kata` | Repository architecture and model-shape conventions |
| `sqb test` | Transformation behavior |
| `sqb audit` | Data quality against materialized data |

Kata is a separate command. It is not run automatically by `compile` or `build`.

### Enable Kata

Commit the shared policy to `sqlbuild_project.toml`:

```toml
[kata]
select = ["SQBK"]
```

This activates the complete standard policy. Start here, then use `ignore` to switch off conventions
the repository is not ready to enforce.

Kata evaluates no rules when `[kata].select` is empty. Prefixes select matching rules that are
enabled by default; exact codes also select individually opt-in rules. All current built-ins are
enabled by default, so `SQBK` selects the complete built-in catalogue.

Rule selectors are case-sensitive prefixes. They do not use `*` wildcards:

- Built-in rules use `SQBK<family><three digits>`, such as `SQBKS101`.
- Custom rules use `XSQBK<family><three digits>`, such as `XSQBKP001`.
- `select` activates rules; `ignore` removes matching rules from the active policy.
- An exact code activates that rule even when it is opt-in.
- The CLI `--select` and `--exclude` flags scope models, not rules.

Inspect any built-in or configured custom rule without enabling it:

```bash
sqb kata rule SQBKS101
```

### Built-in rules

All current built-ins form the standard policy and are enabled by matching prefixes.

#### Structure

| Code | Check |
|------|-------|
| `SQBKS000` | Standalone comments belong on the first inner line of a CTE |
| `SQBKS001` | Transformation logic belongs in top-level CTEs |
| `SQBKS002` | The terminal SELECT reads plainly from the final top-level CTE |
| `SQBKS101` | Each `__ref` and `__source` is isolated in one dependency import CTE |
| `SQBKS201` | `SELECT *` is restricted to dependency import CTEs |
| `SQBKS202` | Positional set-operation branches enumerate their columns |
| `SQBKS301` | CTEs are top-level, not nested |
| `SQBKS302` | Recursive CTEs are not permitted |
| `SQBKS401` | View materialization agrees with the `stg_v`, `int_v`, or `mart_v` marker |
| `SQBKS501` | CTE names describe their contents |

#### Layers and model grammar

| Code | Check |
|------|-------|
| `SQBKL001` | Dependencies flow forward through the layer order |
| `SQBKL101` | Qualified table dependencies use `__ref` or `__source` |
| `SQBKR001` | Model names follow `<domain>__<layer>__<entity>[__<source>]` |
| `SQBKR002` | Model layer names agree with their folders |
| `SQBKR201` | Model source suffixes and source dependency names use approved, current tokens |
| `SQBKR301` | Referenced model identifiers follow Kata model-name grammar |
| `SQBKR401` | Models declare `contract enforced` |
| `SQBKR500` | Every model resolves to one configured domain root and level |
| `SQBKR501` | Every model owner is a leaf or a branch, never both |
| `SQBKR502` | Ownership paths stay within `max_subdomain_depth` |
| `SQBKR503` | Compressed underscore-token prefixes do not hide implicit owners |

#### Owner layout

Kata treats warehouse levels as an axis beneath a genuine domain root. Levels are configurable and
may contain more than one path component:

```toml
[kata.layout]
levels = ["staging", "intermediate/clean", "intermediate/enriched", "mart"]
domain_roots = ["market/betfair", "model/horsenet/ratings"]
```

`domain_roots` is optional. Without it, Kata infers the complete domain root as every path component
between `models/` and the configured level. If more than one configured level can interpret a path,
`SQBKR500` reports every candidate instead of guessing. Add explicit roots for those ambiguous
trees. Level paths and explicit domain roots must be normalized, unique, and non-overlapping.

The standard owner shapes are:

```text
models/<domain>/<level>/<model>.sql
models/<domain>/<level>/<subdomain>/<model>.sql
```

At every ownership node, direct models make the node a leaf and child owners make it a branch. A
directory may not contain both. Different branches may terminate at different depths; Kata does not
require empty ceremonial folders merely to make paths the same length.

`max_subdomain_depth` defaults to one and counts only owners after the configured level. Domain-root
components, composite-level components, declaration roles, and declaration-role buckets do not
count. Projects can raise the non-negative threshold explicitly:

```toml
[kata.thresholds]
max_subdomain_depth = 2
```

Kata detects ownership hidden in flattened underscore names with a compressed token trie. Unary
token chains remain compound terms, so `barrier_trial/` and `barrier_trial_analysis/` identify
`barrier_trial` rather than `barrier`. Real branch points remain explicit: Salesforce annotation
export, annotation validation, and events identify an outer `salesforce` owner and an inner
`annotation` concern. Detection starts with two siblings by default:

```toml
[kata.thresholds]
min_shared_owner_prefix_directories = 2
```

Set this threshold to zero to disable the prefix-family check.

#### Joins

| Code | Check |
|------|-------|
| `SQBKJ001` | Implicit comma joins are not permitted |
| `SQBKJ002` | Cross joins require an exact, reasoned exception |
| `SQBKJ101` | Non-cross joins declare `ON` or `USING` keys |

#### Column naming and types

| Code | Check |
|------|-------|
| `SQBKN001` | `is_`, `has_`, and `can_` columns are BOOLEAN |
| `SQBKN002` | `*_at`, `*_ts`, and `*_timestamp` columns use timestamp types |
| `SQBKN003` | `*_date` columns are DATE |

These checks use declared contract columns, not inferred output columns.

#### Decision hygiene

| Code | Check |
|------|-------|
| `SQBKH001` | Enum comparisons use declared members and normalized operands |
| `SQBKH002` | Non-canonical numeric decisions use named constants |
| `SQBKH101` | Identical enum domains are consolidated |
| `SQBKH201` | Public enum and constant files live under domain folders |
| `SQBKH301` | Declaration role containers are flat or fully grouped |
| `SQBKH302` | Declaration role buckets stay within their configured depth |
| `SQBKH303` | Flat roles and individual buckets stay within file-count caps |
| `SQBKH304` | Buckets use specific concern names rather than generic role names |
| `SQBKH305` | Shared filename prefixes become navigation buckets |

`SQBKH001` requires direct comparisons to `@enum("<enum>").<MEMBER>`. Normalize controlled values
upstream rather than wrapping either comparison operand. A direct source-side value may be
normalized in the comparison because the project does not control source casing; the enum member
must still remain unwrapped.

The declaration-container rules apply to public and private `macros`, `constants`, and `enums`
roles. A container is either flat or every file is grouped into one level of concern buckets:

```text
_macros/                       _macros/
├── normalise_name.py          ├── normalisation/
└── resolve_match.py           │   └── names.py
                               └── resolution/
                                   └── matches.py
```

Buckets are navigation only. They never change the declaration owner or compiler visibility.
Generic buckets such as `utils`, `common`, `shared`, and `misc` fault. Defaults are:

```toml
[kata.thresholds]
max_role_container_depth = 1
max_macro_container_files = 10
max_constant_container_files = 10
max_enum_container_files = 10
min_shared_container_prefix_files = 2
```

#### Tests and coverage

| Code | Check |
|------|-------|
| `SQBKX001` | Non-passthrough models meet the configured audit minimum |
| `SQBKX002` | Non-passthrough models meet the configured SQL test minimum |
| `SQBKX201` | Selected custom rules have statically discoverable public-harness test cases |

Selecting a custom rule automatically adds `SQBKX201` unless the policy ignores it. This is a
static check for conventional `RuleCase` and `evaluate_rule` usage; it does not execute the tests.
Thresholds default to one and can be set to zero to disable the corresponding minimum:

```toml
[kata.thresholds]
min_audits_per_model = 1
min_tests_per_model = 1
min_custom_rule_test_cases = 1
```

#### SQL tests and scenarios

The `SQBKT` family governs SQL authored under `tests/unit/` and `tests/scenarios/`. It consumes
compiler-resolved test targets and resource ownership; it does not infer ownership from filenames
or repeat compiler diagnostics for malformed tests.

| Code | Check |
|------|-------|
| `SQBKT001` | Unit tests and scenarios use their compiler-owned canonical roots |
| `SQBKT002` | Unit and scenario filenames identify their subject and behavior |
| `SQBKT003` | Unit tests mirror resolved model, macro, UDF, or table-function ownership |
| `SQBKT004` | Every `TEST` block has an explicit target-aware `subject__expected_behavior` name |
| `SQBKT101` | Scenario descriptions identify a concrete business behavior rather than generic case numbering |

Select the family independently when adopting these conventions:

```toml
[kata]
select = ["SQBKT"]
```

Every unit-test block, including the only block in a file, has an explicit name:

```sql
TEST (
  name "stg_orders__excludes_cancelled_orders",
);
```

The double underscore immediately following the resolved subject separates it from nonempty
behavior. This keeps identities such as `race__mart_v_entry` valid as complete subjects.
Single-model subjects match the resolved expected model, direct-mode subjects match the tested
macro, UDF, or table function, and multi-model subjects name the common domain or an explicit
pipeline. Single underscores separate words within either part. Generic values such as `test`,
`works`, `basic`, and `case_1` are rejected without maintaining a verb allowlist.

Unit filenames use either `test_<subject>.sql` or `test_<subject>__<behavior>.sql`. When a behavior
suffix is present, it corresponds to the behavior portion; concise prefixes such as
`excludes_cancelled` for `excludes_cancelled_orders` are valid. Scenario filenames omit the
redundant prefix and use `<subject>__<behavior>.sql`:

```text
tests/unit/staging/test_stg_orders__excludes_cancelled.sql
tests/scenarios/daily_revenue__multiple_orders.sql
```

Mirroring uses compiled relationships:

- A single-model test mirrors the model parent below its compiler-owned model root.
- A multi-model test mirrors the nearest common model-domain parent.
- Models with no meaningful common parent use the configured pipeline directory.
- Macro, UDF, and table-function tests mirror all resolved direct resource owners.
- When ownership cannot be proven from compiler facts, Kata skips mirroring rather than guessing.

The pipeline directory is relative to `tests/unit/`, normalized, and included in cache and generated
guidance identity. The default is `pipelines`:

```toml
[kata.sql_tests]
pipeline_directory = "chains/commerce"
```

This maps cross-domain tests to `tests/unit/chains/commerce/`. Absolute paths, traversal, repeated
separators, and backslash paths are invalid configuration.

### Naming policy

Naming and layer rules can use a closed project vocabulary:

```toml
[kata]
domains = ["finance", "market"]
approved_source_tokens = ["salesforce", "stripe"]
cte_name_whitelist = ["finalized_rows"]
cte_name_denylist = ["scratch_result"]

[kata.retired_source_tokens]
old_crm = "salesforce"
```

Valid Kata layers are `stg`, `stg_v`, `int_clean`, `int_v`, `int_enriched`, `mart`, and
`mart_v`. Configuration supplies vocabulary to active rules; it does not activate them. When
`SQBKR001` or `SQBKH201` is active, a non-empty `domains` list constrains model or declaration
domains respectively.

### Exceptions and scoped ignores

Choose the narrowest mechanism that represents the policy:

| Mechanism | Scope | Reason required | Stale-checked |
|-----------|-------|-----------------|---------------|
| `ignore` | Disable rules globally | No | No |
| `rule_exceptions` | One exact rule and exact file | Yes | Yes |
| `rule_ignores` | Rule prefixes or codes across path globs | Yes | No |
| `select_star_allow` | Path-glob allowance for `SQBKS201` | Yes | No |

```toml
[[kata.rule_exceptions]]
rule = "SQBKJ002"
path = "models/mart/market__mart__matrix.sql"
reason = "Intentional Cartesian product over a bounded dimension"

[[kata.rule_ignores]]
rules = ["SQBKS"]
paths = ["models/legacy/**"]
reason = "Legacy migration boundary"

[[kata.select_star_allow]]
paths = ["models/mart/*_export.sql"]
reason = "Intentional passthrough export"
```

An exact exception fails when its active rule no longer produces a fault at that file, prompting
the repository to remove obsolete exceptions. Broad migration boundaries and lone-star allowances
remain reasoned but are intentionally not stale-checked.

### Cache and CI

Built-in policies use a persistent cache under `target/kata-cache`. Compiled model content, active
rules, options, thresholds, naming vocabulary, and relevant project files participate in cache
identity. Disable it when diagnosing cache behavior:

```toml
[kata.cache]
enabled = false
```

Run Kata directly in CI. It exits `1` when faults remain:

```bash
sqb kata
sqb kata --json
```

Generate agent guidance from the same resolved policy and verify that committed guidance remains
fresh:

```bash
sqb kata skills
sqb kata skills --check
```

Kata manages `.agents/skills/sqlbuild-kata/SKILL.md`,
`.claude/skills/sqlbuild-kata/SKILL.md`, and `.opencode/skills/sqlbuild-kata/SKILL.md`. It refuses
to overwrite divergent or unowned files.

See [Custom Kata Rules](/concepts/kata/custom-rules) to encode repository-specific policy and the
[Kata CLI reference](/cli/kata) for command output and exit behavior.

## Custom Kata Rules

Source: `concepts/kata/custom-rules.mdx`

Define and test repository-owned SQL architecture rules with the public Kata API.

Custom Kata rules extend the built-in policy when a repository has domain conventions that cannot
be expressed by configuration alone. They use the same selection, suppression, deterministic
ordering, and remediation output as built-ins.

Custom rule codes use `XSQBK<family><three digits>`. Keep codes stable after adoption because they
become part of configuration, CI output, and exceptions.

### Define a rule

```python
from sqlbuild.kata import KataFault, RuleContext, kata

@kata(
    code="XSQBKP001",
    family="prices",
    slug="typed-currency",
    message="price models must declare a currency column",
    remediation="Declare currency in the MODEL columns contract.",
)
def typed_currency(*, model, ctx: RuleContext) -> list[KataFault]:
    if any(column.name == "currency" for column in ctx.declared_columns):
        return []
    return [ctx.path_fault()]
```

The function signature is exactly two keyword-only arguments named `model` and `ctx`. Return an
empty list when the model passes or one or more `KataFault` values when it fails.

`RuleContext` exposes the compiled model, authored SQL, raw Polyglot AST, references, parsed model
name, materialization, declared columns, audit and test counts, public declarations, active policy,
and fault constructors. Repository files can be read safely through `project_read_text` and
`project_glob`.

### Load and select rules

Load repository-owned files or dotted modules from `sqlbuild_project.toml`:

```toml
[kata]
select = ["XSQBKP001"]
rule_paths = ["kata/rules"]
rule_modules = ["project_kata.rules"]
```

A directory in `rule_paths` is scanned recursively for Python files containing `@kata`. Dotted
modules must resolve beneath the project root. Codes must be unique across built-in and custom
rules.

Custom rules require exact selectors by default. Set `enabled_by_default=True` on the decorator to
include a rule in matching prefix selections. This does not activate Kata when
`[kata].select` is empty.

### Typed options

Declare options with `RuleOption.boolean`, `integer`, `string`, `string_list`, or `integer_list`:

```python
from sqlbuild.kata import KataFault, RuleContext, RuleOption, kata

REQUIRED_DOMAIN = RuleOption.string(
    name="required_domain",
    default="market",
    description="Domain that owns price models",
)

@kata(
    code="XSQBKP002",
    family="prices",
    slug="required-domain",
    message="price models must belong to the configured domain",
    remediation="Move or rename this model for the configured domain.",
    options=(REQUIRED_DOMAIN,),
)
def required_domain(*, model, ctx: RuleContext) -> list[KataFault]:
    parts = ctx.name_parts
    if parts is not None and parts.domain == ctx.option(REQUIRED_DOMAIN):
        return []
    return [ctx.path_fault()]
```

Configure options under the exact rule code. Unknown rules, option names, or invalid values fail
configuration:

```toml
[kata.rule_options.XSQBKP002]
required_domain = "finance"
```

### Test every rule

Use the public harness so tests exercise normal SQLBuild discovery, compilation, rule loading, and
structured fault evaluation:

```python
from sqlbuild.kata import RuleCase, evaluate_rule

from kata.rules.prices import typed_currency

def test_missing_currency_faults() -> None:
    result = evaluate_rule(
        rule=typed_currency,
        test_case=RuleCase(
            description="missing currency faults",
            source=(
                "MODEL (materialized table);\n\n"
                "WITH final AS (SELECT 1 AS price)\n"
                "SELECT price FROM final\n"
            ),
            path="models/mart/market__mart__prices.sql",
            expected_fault_count=1,
        ),
    )

    assert result.fault_count == 1
```

`RuleCase.files` can add supporting project files and `RuleCase.config` supplies the rule's option
values. Keep conventional `RuleCase` and `evaluate_rule` calls under `tests/` so `SQBKX201` can
count statically discoverable harness cases. This coverage check does not execute the tests, so run
the test suite separately in CI.

### Execution and caching

Selected custom rules execute in a bounded Python subprocess with a 30-second timeout. Exceptions
are reported with the rule code and model path, and returned faults rejoin normal suppressions and
deterministic ordering.

Selecting any custom rule disables the model cache by default. To keep the built-in cache available,
require hermetic custom rules explicitly:

```toml
[kata.cache]
enabled = true
require_cacheable = true
```

Cacheable rules may import supported pure modules such as `collections`, `dataclasses`, `enum`,
`math`, `re`, `typing`, and `sqlbuild.kata`. Use `RuleContext` rather than direct filesystem calls.
SQLBuild validates these constraints before evaluation.

Custom findings are still recomputed on each invocation. `require_cacheable` preserves the native
model cache around them; it does not cache custom subprocess output.

Return to [Kata SQL Architecture Checks](/concepts/kata) for built-in rules, selectors, and
exceptions.

## Overview

Source: `concepts/python-nodes/overview.mdx`

Tasks, assets, loaders, and checks as first-class nodes in the SQLBuild graph.

Python nodes let your project grow beyond warehouse-only SQL while keeping the SQL graph clean. They are ordinary Python functions, decorated to become nodes in the same DAG as your SQL models, and they run as part of `sqb build`.

There are four kinds, authored in dedicated top-level folders:

| Kind | Decorator | Folder | Purpose |
|------|-----------|--------|---------|
| Loader | `@loader` | `loaders/` | Load external data into a managed source |
| Task | `@task` | `tasks/` | Run Python computation or side effects |
| Asset | `@asset` | `assets/` | Produce or observe an external artifact |
| Check | `@check` | `checks/` | Validate tasks, assets, and loaders |

All four share the same decorator conventions, dependency model, selection syntax, and runtime context helpers. The pages for each kind cover their specifics:

- [Loaders](/concepts/python-nodes/loaders) - load data into managed sources
- [Tasks](/concepts/python-nodes/tasks) - Python computation and side effects
- [Assets](/concepts/python-nodes/assets) - external artifacts
- [Checks](/concepts/python-nodes/checks) - Python validations
- [Factories](/concepts/python-nodes/factories) - generate nodes programmatically with `@factory`
- [SQL references](/concepts/python-nodes/sql-references) - read SQL models and sources from Python

Nodes can also be generated programmatically with [`@factory`](/concepts/python-nodes/factories) instead of authored one at a time.

### The SQL boundary

The most important rule: **SQL models never depend on Python nodes.** The dependency direction is strictly one way.

- SQL models depend only on other SQL resources (models, sources, seeds, functions).
- Python nodes may depend on other Python nodes.
- The only way Python data reaches SQL is through a **loader populating a source**: `loader -> source -> model`.
- Python nodes may **read** SQL models and sources at runtime through typed references (see [SQL references](/concepts/python-nodes/sql-references)), but reading a model does not make it a SQL dependency.

This keeps the SQL graph fully analyzable and testable on its own, while letting Python participate around the edges.

```
            depends_on
  task ----------------> task
   |                       |
   | (read only)           v
   |                     asset
   v                       |
 source <-- loader         | check (validates tasks/assets/loaders)
   |
   v
 model (SQL) ----> model (SQL)
```

### Decorators

Every decorator accepts the same organizational metadata:

| Argument | Description |
|----------|-------------|
| `depends_on` | A single function, tuple, or list of upstream nodes (and, where allowed, `model()`/`source()` references) |
| `tags` | Labels for selection, filtering, and catalog grouping |
| `group` | A display/catalog grouping string |
| `description` | Human-readable docs (defaults to the function docstring) |
| `meta` | Freeform JSON metadata for catalogs and integrations |

`@task` and `@asset` also accept a `retry` policy. `@asset` additionally accepts `columns` and `column_lineage`. Node kind is inferred from the decorator - you never pass `kind=`.

### Identity tracking

Every Python node is fingerprinted by source code hash, decorator config hash, and transitive dependency hashes (scoped to the git root, so third-party package updates don't affect identities). The plan shows source and dependency diffs when a node's identity changes, giving you visibility into what changed in your Python code.

Unlike SQL models, Python nodes may depend on external inputs the framework cannot observe (APIs, files, third-party services). Skip/run decisions are therefore user-controlled via `ctx.skip()`: the node's own logic decides whether it needs to run. See [Planning and Change Detection](/concepts/planning#python-nodes) for details.

### Runtime context

Each node receives a context object as its first argument (`TaskContext`, `AssetContext`, `CheckContext`, or `LoaderContext`). They share these helpers:

| Helper | Description |
|--------|-------------|
| `ctx.run_id` | Unique identifier for this run |
| `ctx.target` | Active target name |
| `ctx.vars` | Project variables |
| `ctx.is_reload` | `True` when `--reload` was passed |
| `ctx.adapter` / `ctx.connection` | Adapter and live connection |
| `ctx.log(message)` | Log to the run output |
| `ctx.query(sql)` / `ctx.execute_sql(sql)` | Run SQL on the connection |
| `ctx.qualify_name(name)` | Qualify a relation name |
| `ctx.relation(ref)` | Resolve a declared `model()`/`source()` reference to a relation |
| `ctx.result_of(node_fn)` | Read the latest persisted result of an upstream node (current or previous run) |
| `ctx.results_of(node_fn, limit=N)` | Read the last N successful results of an upstream node, newest first |
| `ctx.providers` | Access discovered [providers](/concepts/python-nodes/providers) by name |

Task and asset contexts add `ctx.result(...)` and `ctx.skip(...)`. Check contexts add `ctx.pass_(...)`, `ctx.fail(...)`, and `ctx.warn(...)`.

Providers can also be injected directly as function parameters by name. See [Providers](/concepts/python-nodes/providers) for details.

### Returns and skips

Tasks and assets return through `ctx.result(...)`:

```python
@task
def export_orders(ctx):
    return ctx.result(payload={"rows": 120}, metadata={"rows": 120})
```

- A plain value or `None` is also accepted and normalized to a successful result.
- `ctx.skip(reason, mode=...)` skips the node. `mode` accepts `"soft"` (default, skips only this node) or `"hard"` (also blocks dependents), as a string or the `SkipMode` enum from `sqlbuild.tasks`/`sqlbuild.assets`.
- Assets may pass `materialized=True`/`False` to record whether an artifact was produced.

Downstream nodes run only if at least one upstream succeeded. If all upstreams are skipped, the downstream is skipped. A failed or hard-skipped upstream blocks its dependents.

### Result persistence

Node results (payload, metadata, status, errors) are persisted after each execution. In direct mode, results are stored in `_sqlbuild_node_results` in the warehouse alongside your data. In virtual mode, results are stored in the VDE state backend scoped per environment. Results persist across runs, so they are available for observability, debugging, and downstream consumption.

### Selection

Python nodes are selected like SQL resources, by bare name or typed selector:

```bash
sqb build --select export_orders          # bare name
sqb build --select task:export_orders      # typed
sqb build --select asset:orders_export
sqb build --select check:check_orders
sqb build --select tag:exports             # by tag
sqb build --select +orders_export           # with upstreams
```

Names are globally unique across models, sources, seeds, functions, loaders, tasks, assets, checks, providers, and hooks.

### Lifecycle: run, build, check

Python nodes run in two phases relative to SQL:

- **Ingress (pre-SQL):** loaders, and tasks/assets that feed sources, run before SQL models are built.
- **Read-side (post-SQL):** tasks/assets that read SQL run after their SQL dependencies are built.

The commands differ in what they include by default:

| Command | SQL | Loaders / tasks / assets | Checks | Audits |
|---------|-----|--------------------------|--------|--------|
| `sqb build` | Yes | Yes | Yes | Yes |
| `sqb build --no-tests --no-audits` | Yes | Yes | No | No |
| `sqb check` | No | No | Selected checks only | No |

- `sqb build` is the complete build-and-validate command: it runs SQL, the required Python nodes, SQL audits, and Python checks.
- `sqb build --no-tests --no-audits` executes the DAG without validation, for fast iteration.
- `sqb check` runs Python checks only. See [`sqb check`](/cli/check).

Use `--no-python` on `plan` and `build` to suppress read-side tasks/assets. Loader-side Python required to populate selected sources still runs (use `--no-load` to skip source loading). See the [`sqb build`](/cli/build) reference.

### Try it

The `python_nodes` playground is a small working project with a task, loader, model, asset, and check:

```bash
sqb playground --template python_nodes
cd sqlbuild-playground
sqb build --select +fact_orders --select +orders_export
sqb check --select +check_orders_export
```

See [`sqb playground`](/cli/playground).

## Loaders

Source: `concepts/python-nodes/loaders.mdx`

Load external data into source tables with Python functions.

Loaders are Python functions that load data into source tables. They replace expression sources and manual ETL scripts with code that lives inside your project, runs as part of the build, and supports incremental write strategies. Loaders are one of the four [Python node](/concepts/python-nodes/overview) kinds, and the only one that writes into a SQL source.

### How it works

1. Write a Python function under `loaders/` decorated with `@loader`
2. Declare a managed source in `sources/*.yml` with `managed: true` and **the same name as the loader function**
3. SQLBuild calls the function, writes returned rows to a staging table, then applies the configured write strategy to the target

Loaders participate in the build lifecycle. When `sqb build` runs, managed sources are loaded before any dependent model is materialized.

### Defining a loader

Place Python files under `loaders/` in your project directory. Each file can contain one or more loader functions:

```python
# loaders/raw_sources.py
from sqlbuild.loaders import loader
from sqlbuild.executor.load.models import LoaderContext

@loader
def raw_customers(ctx: LoaderContext) -> list[dict[str, object]]:
    return [
        {"id": 1, "name": "Leslie Knope", "email": "leslie@pawnee.gov"},
        {"id": 2, "name": "Ron Swanson", "email": "ron@pawnee.gov"},
    ]
```

The function receives a `LoaderContext` and returns rows as a list of dicts, an iterator of dicts, or `None` for self-managed loaders.

### Binding to a source

Declare a managed source in `sources/*.yml`. A managed source is bound to the loader function **with the same name** - there is no separate `loader` field:

```yaml
sources:
  - name: raw_customers
    managed: true
    write_strategy: table
    columns:
      - name: id
        type: INTEGER
      - name: name
        type: VARCHAR
      - name: email
        type: VARCHAR
```

Setting `managed: true` makes this a **managed source** - SQLBuild owns both the loading and the schema. The binding is by name: the source `raw_customers` is populated by the `@loader` function named `raw_customers`. SQLBuild raises an error if a managed source has no loader function of the same name.

Models reference managed sources the same way as any other source:

```sql
SELECT id, name FROM __source("raw_customers")
```

### Write strategies

The `write_strategy` field controls how returned rows are written to the target table.

#### table

Full replace. The target is dropped and recreated from the loader output on every run.

```yaml
sources:
  - name: raw_countries
    managed: true
    write_strategy: table
    columns:
      - name: country_id
        type: INTEGER
      - name: country_code
        type: VARCHAR
```

#### append

Insert all returned rows into the target. No deduplication.

```yaml
sources:
  - name: raw_webhook_events
    managed: true
    write_strategy: append
    columns:
      - name: event_id
        type: INTEGER
      - name: event_name
        type: VARCHAR
```

#### delete_insert

Delete rows in the cursor range, then insert replacements. Requires `cursor_column`.

```yaml
sources:
  - name: raw_order_events
    managed: true
    write_strategy: delete_insert
    cursor_column: event_at
    columns:
      - name: event_id
        type: INTEGER
      - name: event_at
        type: TIMESTAMP
      - name: amount_cents
        type: INTEGER
```

The loader receives `ctx.current_cursor_value` with the current `MAX(cursor_column)` from the target, so it can fetch only new or updated data. Its function name matches the source name (`raw_order_events`):

```python
@loader
def raw_order_events(ctx: LoaderContext) -> list[dict[str, object]]:
    if ctx.current_cursor_value is None:
        return fetch_all_events()
    return fetch_events_since(ctx.current_cursor_value)
```

#### merge

Upsert based on `unique_key`. Requires both `unique_key` and `cursor_column`.

```yaml
sources:
  - name: raw_customers
    managed: true
    write_strategy: merge
    unique_key: customer_id
    cursor_column: updated_at
    columns:
      - name: customer_id
        type: INTEGER
      - name: plan_name
        type: VARCHAR
      - name: updated_at
        type: TIMESTAMP
```

Existing rows matching the unique key are updated; new rows are inserted.

### Self-managed loaders

If a loader returns `None`, SQLBuild skips its row-writing pipeline. The loader is responsible for writing data to the target itself, using whatever approach makes sense - `ctx.execute_sql()`, an external library, a subprocess, or anything else:

```python
@loader
def raw_status(ctx: LoaderContext) -> None:
    ctx.execute_sql(f"DROP TABLE IF EXISTS {ctx.destination}")
    ctx.execute_sql(
        f"CREATE TABLE {ctx.destination} AS "
        "SELECT 1 AS status_id, 'loaded' AS status_name"
    )
```

The source is still declared as managed, just without a `write_strategy`:

```yaml
sources:
  - name: raw_status
    managed: true
    columns:
      - name: status_id
        type: INTEGER
      - name: status_name
        type: VARCHAR
```

Self-managed loaders must not declare a `write_strategy`. They are useful when you want to use adapter-specific SQL (e.g. `COPY INTO`, external tables), call an external ingestion tool like [dlt](/integrations/dlt), or handle writes in a way that doesn't fit the dict-return pattern.

### Loader context

Every loader function receives a `LoaderContext` as its first argument. It provides access to the destination relation, cursor state, active target, and helper methods.

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `destination` | `str` | Fully-qualified destination relation name (where rows are written) |
| `destination_database` | `str \| None` | Destination database |
| `destination_schema` | `str \| None` | Destination schema |
| `destination_name` | `str` | Unqualified destination table name |
| `current_cursor_value` | `object \| None` | Current `MAX(cursor_column)` from the destination, or `None` if the table does not exist or has no cursor column |
| `run_id` | `str` | Unique identifier for this execution run |
| `target` | `str \| None` | Active target name (e.g. `dev`, `prod`) |
| `vars` | `dict` | Project variables (merged from project, target, and local config) |
| `is_reload` | `bool` | `True` when `--reload` was passed |
| `start_cursor_ts` | `datetime \| None` | Timestamp cursor start override from `--start-cursor-ts` |
| `end_cursor_ts` | `datetime \| None` | Timestamp cursor end override from `--end-cursor-ts` |
| `start_cursor_int` | `int \| None` | Integer cursor start override from `--start-cursor-int` |
| `end_cursor_int` | `int \| None` | Integer cursor end override from `--end-cursor-int` |
| `adapter` | `BaseAdapter` | The database adapter instance |
| `connection` | `object` | The active database connection |
| `logger` | `Logger` | Python logger scoped to the loader |

#### Methods

| Method | Description |
|--------|-------------|
| `execute_sql(sql)` | Execute a SQL statement against the connection |
| `query(sql)` | Execute a SQL query and return the cursor |
| `log(message)` | Log a message to the execution lifecycle output |
| `qualify_name(name)` | Return a fully-qualified relation name in the destination database/schema |
| `skip(reason, mode=...)` | Skip this loader. `mode` is `"soft"` (default, skip only this loader) or `"hard"` (also block dependents) |
| `result(payload=, metadata=, materialized=)` | Return a structured result for a self-managed loader |
| `result_of(node_fn)` | Read the latest persisted result of an upstream node (current or previous run) |
| `results_of(node_fn, limit=N)` | Read the last N successful results of an upstream node, newest first |
| `loader(loader_fn)` | Return a `LoaderRelationRef` for an upstream loader dependency |
| `source(source_name)` | Return a `LoaderRelationRef` for a project source by YAML name |

#### LoaderRelationRef

Returned by `ctx.loader()` and `ctx.source()`. Provides access to an upstream relation:

| Property / Method | Description |
|-------------------|-------------|
| `destination` | Fully-qualified relation name |
| `current_cursor_value` | Current `MAX(cursor_column)` from the relation |
| `max(column)` | Return the `MAX` of any column from the relation |

### Loader dependencies

Loaders can depend on other loaders using `depends_on`. Dependencies are executed first, and their destination relations are available via `ctx.loader()`:

```python
from sqlbuild.loaders import loader
from sqlbuild.executor.load.models import LoaderContext

@loader
def raw_accounts(ctx: LoaderContext) -> list[dict[str, object]]:
    return [
        {"account_id": 1, "account_name": "Pawnee Parks"},
        {"account_id": 2, "account_name": "Eagleton"},
    ]

@loader(depends_on=[raw_accounts])
def raw_account_metrics(ctx: LoaderContext) -> list[dict[str, object]]:
    accounts = ctx.loader(raw_accounts)
    rows = ctx.query(f"SELECT account_id FROM {accounts.destination}")
    return [
        {"account_id": row[0], "metric": "active"}
        for row in rows.fetchall()
    ]
```

Dependencies form a DAG. SQLBuild schedules loaders in topological order and executes independent loaders concurrently when `--concurrency` is set.

Intermediate loaders (those referenced only via `depends_on`, with no managed source of the same name) are given synthetic source entries and write to `__loader__<name>` tables by default. Only the terminal loader - the one whose name matches a managed source - populates that source; intermediate loaders feed it. Use the `destination` parameter on the decorator to override the intermediate relation:

```python
@loader(destination="staging.shared_accounts")
def raw_accounts(ctx: LoaderContext):
    ...
```

### Decorator parameters

The `@loader` decorator accepts optional parameters that can also be set in the source YAML. When both are specified, the YAML takes precedence.

| Parameter | Description |
|-----------|-------------|
| `depends_on` | List of loader functions this loader depends on |
| `destination` | Override the destination relation name (can include schema or database) |
| `write_strategy` | `table`, `append`, `delete_insert`, or `merge` |
| `cursor_column` | Column used for incremental cursor tracking |
| `unique_key` | Column(s) used as the merge key (string or list of strings) |
| `columns` | Column specifications with name, type, nullable, and description |
| `contract` | `enforced` or `none` |

### Auto-load during builds

By default, `sqb build` automatically loads managed sources before building dependent models. This is controlled by the `auto_load_sources` setting:

```toml
[settings]
auto_load_sources = true   # default
```

You can also control this per-run with CLI flags:

```bash
# Explicitly load sources before building
sqb build --load

# Skip source loading
sqb build --no-load

# Reload sources (passes is_reload=True to loaders)
sqb build --reload
```

When `--reload` is passed, `ctx.is_reload` is `True` in the loader function. This lets loaders implement different behavior for full reloads versus normal incremental loads.

### Source deferral

Loader writes and managed source reads are resolved separately. `loader_schema` controls
where a target's loaders write; `defer_sources_to` optionally selects another target whose
managed sources models should read.

```toml
[targets.dev]
schema = "analytics_dev"
loader_schema = "raw_dev"
defer_sources_to = "prod"

[targets.prod]
schema = "analytics_prod"
loader_schema = "raw_prod"
```

With this config:

- `sqb load --target dev` writes to `raw_dev`.
- `sqb load --target prod` writes to `raw_prod`.
- Models built in dev read from `raw_prod` because dev defers source reads to prod.
- Models built in prod read from `raw_prod` because omitted deferral defaults to the active target.

If `loader_schema` is omitted, loaders fall back to the active target's model `schema`, then
the adapter default schema. An explicit `schema` on a managed source overrides the target
default. SQLBuild validates final managed-loader write namespaces and rejects two targets
on the same warehouse/database that could write to the same schema.

`defer_sources_to` never redirects loader writes. It only changes `__source()` and Python
`source()` reads. This lets developers test loaders in an isolated schema without making
development models consume partial development source data.

### Schema evolution

When a loader returns rows with columns not present in the existing target table, SQLBuild detects the schema change and adds the new columns automatically. Type mismatches between the staging table and the existing target raise an error.

### Project structure

```
my-project/
  loaders/
    raw_sources.py          # loader functions
    api_sources.py           # more loader functions
  sources/
    raw.yml                  # managed source declarations (managed: true)
  models/
    staging/
      stg_customers.sql      # __source("raw_customers")
```

SQLBuild discovers all `.py` files under `loaders/` recursively (excluding `__init__.py` and files starting with `_`). Each file is scanned for functions decorated with `@loader`.

### Config reference

#### Source YAML fields for managed sources

| Field | Description |
|-------|-------------|
| `managed` | Set to `true` to bind the source to the `@loader` function of the same name |
| `write_strategy` | `table`, `append`, `delete_insert`, or `merge` (requires `managed: true`) |
| `cursor_column` | Column for incremental cursor tracking (required for `delete_insert` and `merge`) |
| `unique_key` | Merge key column(s) (required for `merge`) |
| `columns` | Column declarations with types |
| `contract` | `enforced` or `none` |

#### Validation rules

- `append` cannot have `unique_key`
- `merge` requires `unique_key`
- `table` cannot have `cursor_column` or `unique_key`
- `delete_insert` requires `cursor_column` and cannot have `unique_key`
- `cursor_column` requires one of `append`, `delete_insert`, or `merge`

## Tasks

Source: `concepts/python-nodes/tasks.mdx`

Run Python computation and side effects as nodes in the SQLBuild graph.

Tasks are Python functions that run as part of the DAG. Use them for computation, side effects, and orchestration steps that are not loading data into a source and not producing a tracked artifact. See [Python Nodes](/concepts/python-nodes/overview) for the shared model and the SQL boundary rules.

### Defining a task

Place Python files under `tasks/` and decorate functions with `@task`:

```python
# tasks/orders.py
from sqlbuild.tasks import task, TaskContext

@task
def export_orders(ctx: TaskContext):
    rows = fetch_orders()
    return ctx.result(payload={"rows": len(rows)}, metadata={"rows": len(rows)})
```

The task receives a `TaskContext` and returns through `ctx.result(...)`. A plain return value or `None` is also accepted and normalized to a successful result.

### Dependencies

Tasks declare dependencies with `depends_on`, accepting a single function, a tuple, or a list:

```python
@task
def fetch_orders(ctx: TaskContext):
    return ctx.result(payload=download_orders())

@task(depends_on=fetch_orders)
def summarize_orders(ctx: TaskContext):
    result = ctx.result_of(fetch_orders)
    return ctx.result(metadata={"count": len(result.payload)})
```

`ctx.result_of(node_fn)` reads the latest persisted result of an upstream node, returning a `NodeResultEnvelope` with `payload`, `metadata`, `status`, and `ts` fields. Results persist across runs. Use `ctx.results_of(node_fn, limit=N)` to read result history. Reading a missing or unsuccessful upstream raises unless you pass `default=`.

Tasks may depend on other tasks, assets, and loaders. They may **not** depend on SQL models or sources as graph dependencies, but they can read them at runtime with typed references - see [SQL references](/concepts/python-nodes/sql-references).

### Returning results

```python
@task
def build_export(ctx: TaskContext):
    return ctx.result(
        payload={"path": "/exports/orders.csv"},
        metadata={"rows": 1200},
    )
```

- `payload` is the value downstream nodes read with `ctx.result_of(...)`.
- `metadata` is structured JSON for catalogs and downstream reads.
- Tasks cannot set `materialized` - that is for [assets](/concepts/python-nodes/assets).

### Skipping

Return `ctx.skip(...)` to skip a task:

```python
@task
def export_if_present(ctx: TaskContext):
    if not new_files_available():
        return ctx.skip("no new files")
    return ctx.result(payload=do_export())
```

- `"soft"` (default) skips only this task; dependents may still run if another upstream succeeded.
- `"hard"` skips this task and blocks its dependents.

`mode` accepts either a plain string or the `SkipMode` enum:

```python
from sqlbuild.tasks import task, SkipMode

@task
def optional_step(ctx):
    return ctx.skip("nothing to do", mode=SkipMode.HARD)  # or mode="hard"
```

### Retries

`@task` accepts a `retry` policy for transient failures:

```python
from sqlbuild.retries import RetryPolicy
from sqlbuild.tasks import task

@task(retry=RetryPolicy(max_attempts=3, retry_on=(ConnectionError,)))
def call_api(ctx):
    return ctx.result(payload=fetch_from_flaky_api())
```

| Field | Default | Description |
|-------|---------|-------------|
| `max_attempts` | `3` | Total attempts including the first |
| `retry_on` | `Exception` | Exception class, tuple, or list to retry on |
| `initial_delay_seconds` | `1.0` | Delay before the first retry |
| `backoff_multiplier` | `2.0` | Exponential backoff multiplier |
| `max_delay_seconds` | `30.0` | Cap on any single delay |
| `max_elapsed_seconds` | `None` | Overall time bound for retries |
| `jitter` | `True` | Randomize delays to avoid synchronized retries |

The default is no retry. Set `retry_on` explicitly rather than relying on the broad default when you can. The original exception is preserved if all attempts fail.

### Decorator parameters

| Parameter | Description |
|-----------|-------------|
| `name` | Override the node name (defaults to the function name) |
| `depends_on` | Upstream nodes (function, tuple, or list); `model()`/`source()` for read-only SQL refs |
| `tags` | Labels for selection and grouping |
| `group` | Display/catalog grouping |
| `description` | Docs (defaults to docstring) |
| `meta` | Freeform JSON metadata |
| `retry` | A `RetryPolicy` |

### Running tasks

```bash
# Run a task and its required graph
sqb build --select export_orders --no-tests --no-audits

# Include in a full build
sqb build --select export_orders
```

Tasks run during `sqb build`. They are not validated by checks unless you also write a [check](/concepts/python-nodes/checks) that depends on them.

## Assets

Source: `concepts/python-nodes/assets.mdx`

Produce or observe external artifacts as nodes in the SQLBuild graph.

Assets are Python nodes that produce or observe an external artifact - an exported file, a published dataset, a dashboard refresh, an ML model. They behave like [tasks](/concepts/python-nodes/tasks) but add dataset-like metadata (columns, column lineage) and a materialization flag. See [Python Nodes](/concepts/python-nodes/overview) for the shared model and the SQL boundary rules.

### Defining an asset

Place Python files under `assets/` and decorate functions with `@asset`:

```python
# assets/exports.py
from sqlbuild.assets import asset, AssetContext

@asset
def orders_export(ctx: AssetContext):
    path = write_orders_csv()
    return ctx.result(metadata={"path": path, "rows": 1200}, materialized=True)
```

The asset receives an `AssetContext` and returns through `ctx.result(...)`.

### Materialization

Assets record whether they actually produced an artifact via `materialized`:

```python
@asset
def orders_export(ctx: AssetContext):
    if nothing_changed():
        return ctx.result(metadata={"status": "unchanged"}, materialized=False)
    return ctx.result(metadata={"path": export()}, materialized=True)
```

- `materialized=True` - the artifact was produced this run.
- `materialized=False` - the asset ran but produced nothing (e.g. it only observed state). This is **not** a skip; the node still succeeded.

Only assets have `materialized`; tasks do not.

### Dependencies

Assets declare dependencies with `depends_on` (a single function, tuple, or list), and may depend on tasks, assets, and loaders:

```python
from sqlbuild.assets import asset
from tasks.orders import export_orders

@asset(depends_on=export_orders)
def orders_dashboard(ctx):
    result = ctx.result_of(export_orders)
    return ctx.result(metadata={"rows": result.payload["rows"]}, materialized=True)
```

To read a SQL model or source, declare a typed reference and resolve it at runtime - see [SQL references](/concepts/python-nodes/sql-references):

```python
from sqlbuild.assets import asset
from sqlbuild.refs import model

@asset(depends_on=model("fact_orders"))
def orders_extract(ctx):
    relation = ctx.relation(model("fact_orders"))
    rows = ctx.query(f"SELECT count(*) FROM {relation}").fetchone()[0]
    return ctx.result(metadata={"rows": rows}, materialized=True)
```

### Columns and column lineage

Assets can declare a schema for catalog and lineage purposes. This does not enforce anything at runtime; it describes the artifact:

```python
@asset(
    columns=[
        {"name": "order_id", "type": "INTEGER"},
        {"name": "total_cents", "type": "INTEGER", "nullable": False},
    ],
    column_lineage={
        "order_id": [{"node": "fact_orders", "column": "order_id"}],
        "total_cents": [{"node": "fact_orders", "column": "total_cents"}],
    },
)
def orders_export(ctx):
    ...
```

- `columns` - column declarations with `name`, optional `type`, `nullable`, `description`, and `meta`.
- `column_lineage` - maps each asset column to upstream `{node, column}` references, surfaced in the DAG artifact and integrations.

Tasks and checks do not support `columns` or `column_lineage`.

### Skipping and retries

Assets support the same `ctx.skip(...)` and `retry` behavior as tasks:

```python
from sqlbuild.assets import asset, SkipMode
from sqlbuild.retries import RetryPolicy

@asset(retry=RetryPolicy(max_attempts=3, retry_on=(IOError,)))
def export(ctx):
    if not ready():
        return ctx.skip("upstream not ready", mode="soft")  # or SkipMode.SOFT
    return ctx.result(metadata={"path": do_export()}, materialized=True)
```

See [Tasks](/concepts/python-nodes/tasks#retries) for the full retry policy fields.

### Decorator parameters

| Parameter | Description |
|-----------|-------------|
| `name` | Override the node name (defaults to the function name) |
| `depends_on` | Upstream nodes (function, tuple, or list); `model()`/`source()` for read-only SQL refs |
| `columns` | Column declarations for the produced artifact |
| `column_lineage` | Map of asset column to upstream `{node, column}` references |
| `tags` | Labels for selection and grouping |
| `group` | Display/catalog grouping |
| `description` | Docs (defaults to docstring) |
| `meta` | Freeform JSON metadata |
| `retry` | A `RetryPolicy` |

### Running assets

```bash
# Run an asset and its required graph
sqb build --select orders_export --no-tests --no-audits

# Include in a full build with its upstreams
sqb build --select +orders_export
```

Assets run during `sqb build`. Use `--no-python` to suppress read-side assets while still loading sources.

## Checks

Source: `concepts/python-nodes/checks.mdx`

Validate tasks, assets, and loaders with Python checks.

Checks are Python nodes that validate other Python nodes. They are the Python analog of SQL [audits](/concepts/audits): audits validate SQL relations, checks validate the output of tasks, assets, and loaders. See [Python Nodes](/concepts/python-nodes/overview) for the shared model.

Checks are separate graph nodes, not callbacks embedded in a task or asset. A check declares what it validates through `depends_on`.

### Defining a check

Place Python files under `checks/` and decorate functions with `@check`. `depends_on` is required:

```python
# checks/orders.py
from sqlbuild.checks import check, CheckContext
from tasks.orders import export_orders

@check(depends_on=export_orders)
def check_orders_exported(ctx: CheckContext):
    result = ctx.result_of(export_orders)
    if result.metadata.get("rows", 0) == 0:
        return ctx.fail("no orders exported")
    return ctx.pass_("orders exported")
```

The check receives a `CheckContext` and reads its dependencies' persisted results with `ctx.result_of(...)`.

### Results

Return a result through the context helpers, or a bool shorthand:

```python
@check(depends_on=orders_asset)
def rows_present(ctx):
    return ctx.result_of(orders_asset).payload["rows"] > 0   # True -> pass, False -> fail
```

| Return | Meaning |
|--------|---------|
| `ctx.pass_(message=None, metadata=None)` | Passing |
| `ctx.fail(message, metadata=None)` | Failing, using the check's severity |
| `ctx.warn(message, metadata=None)` | Warning, regardless of severity |
| `True` | Pass |
| `False` | Fail |

Returning `None` is not allowed - checks must be explicit.

### Severity

`@check` takes a `severity` of `error` (default) or `warn`:

```python
@check(depends_on=export_orders, severity="warn")
def orders_freshness(ctx):
    if stale():
        return ctx.fail("export is stale")   # recorded as a warning, does not fail the build
    return ctx.pass_()
```

- `error` (default) - a failing check fails `sqb build`.
- `warn` - a failing check is reported but does not fail the build.

`ctx.warn(...)` always produces a warning regardless of the declared severity.

### What checks can depend on

- Checks may depend on **tasks, assets, and loaders**.
- Checks may **not** depend on SQL models, sources, seeds, or functions. Use SQL [audits](/concepts/audits) to validate SQL relations.
- Checks may **not** depend on other checks.
- Checks may **not** depend on a terminal source loader directly. Validate loaded source data with a source audit instead.

A check that depends on a single node is displayed grouped under that node. Multi-dependency checks are shown as standalone validation nodes, grouped by `group`, tags, or path.

### Decorator parameters

| Parameter | Description |
|-----------|-------------|
| `depends_on` | Required. Tasks/assets/loaders to validate (function, tuple, or list) |
| `name` | Override the node name (defaults to the function name) |
| `severity` | `error` (default) or `warn` |
| `tags` | Labels for selection and grouping |
| `group` | Display/catalog grouping |
| `description` | Docs (defaults to docstring) |
| `meta` | Freeform JSON metadata |

Checks do not support `columns`, `column_lineage`, or `retry`.

### Running checks

Checks run automatically during `sqb build` when their Python dependencies run. They are skipped when `--no-audits` is passed. To run checks on their own, use [`sqb check`](/cli/check):

```bash
# Run all checks
sqb check

# Run a specific check (and its required dependencies)
sqb check --select +check_orders_exported

# Run checks by tag
sqb check --select tag:exports
```

`sqb check` rejects selecting non-check nodes; use `sqb build` to run tasks and assets. Check results are written to `target/run/checks/python_checks.json`, and `sqb check --json` prints them to stdout.

### Checks vs audits

| | Checks | Audits |
|---|--------|--------|
| Validates | Python tasks, assets, loaders | SQL relations |
| Authored in | `checks/` (Python) | `MODEL()` headers / `audits/` (SQL) |
| Run by | `sqb build`, `sqb check` | `sqb build`, `sqb audit` |
| Severity | `error`, `warn` | `error`, `warn` |

`sqb build` runs both. `sqb audit` runs SQL audits only; `sqb check` runs Python checks only.

## Factories

Source: `concepts/python-nodes/factories.mdx`

Generate Python nodes programmatically with @factory.

A factory is a function that **generates** Python nodes instead of authoring them one at a time. Use `@factory` when you want to create many similar [tasks](/concepts/python-nodes/tasks), [assets](/concepts/python-nodes/assets), [loaders](/concepts/python-nodes/loaders), or [checks](/concepts/python-nodes/checks) from a list, a config, or a loop, rather than hand-writing each one.

Factories are an advanced feature. Most projects author nodes directly; reach for a factory when you find yourself copy-pasting near-identical node definitions.

### Defining a factory

A `@factory` function takes **no arguments** and returns one or more decorated node functions:

```python
# factories/exports.py
from sqlbuild.factories import factory
from sqlbuild.assets import asset

TABLES = ["orders", "customers", "payments"]

@factory
def export_assets():
    nodes = []
    for table in TABLES:
        @asset(name=f"export_{table}", tags=("export",))
        def export(ctx, table=table):
            return ctx.result(metadata={"table": table}, materialized=True)
        nodes.append(export)
    return nodes
```

The returned nodes are discovered and added to the graph exactly as if you had written them by hand. They participate in selection, lifecycle, the DAG artifact, and integrations like any other node.

A factory may return a single node or a list, tuple, or set of nodes. Every returned item must be a decorated `@task`, `@asset`, `@loader`, or `@check` function.

### Folder rules

Where a factory lives determines what it is allowed to emit:

| Location | May emit |
|----------|----------|
| `loaders/` | loaders only |
| `tasks/` | tasks only |
| `assets/` | assets only |
| `checks/` | checks only |
| `factories/` | any kind, including a mix |

- A **single-kind** factory can live in that kind's folder (e.g. an asset-only factory in `assets/`), keeping it next to the nodes it generates. It can also live in `factories/`.
- A factory that emits **more than one kind** must live in `factories/`.

This keeps each kind folder honest: everything in `assets/`, whether hand-written or factory-generated, is an asset.

SQLBuild enforces this at discovery time. A factory in a kind folder that returns a foreign kind raises an error pointing you to `factories/`:

```
Factory export_pipeline in assets/ returned a loader 'raw_orders';
mixed-kind factories must live in factories/.
```

The `factories/` folder is not created by `sqb init` - add it when you need it.

### Mixed-kind factories

A factory in `factories/` can generate a whole related pipeline at once - a loader, the asset that reads it, and a check on the result:

```python
# factories/orders.py
from sqlbuild.factories import factory
from sqlbuild.loaders import loader
from sqlbuild.assets import asset
from sqlbuild.checks import check

@factory
def orders_pipeline():
    @loader(name="raw_orders")
    def load(ctx):
        return fetch_orders()

    @asset(name="orders_export", depends_on=load)
    def export(ctx):
        return ctx.result(materialized=True)

    @check(depends_on=export)
    def orders_export_check(ctx):
        return ctx.pass_("export ready")

    return [load, export, orders_export_check]
```

Generated nodes follow the same rules as directly-authored ones, including the [SQL boundary](/concepts/python-nodes/overview#the-sql-boundary): a factory-generated loader still binds to a managed source, and a factory-generated check still may not depend on SQL models.

### Naming

Generated nodes need unique names across the project. Pass an explicit `name=` to each node a factory creates (factories almost always generate names from a loop variable or config), since relying on the function's own name would produce duplicates.

## Providers

Source: `concepts/python-nodes/providers.mdx`

Shared runtime services for Python nodes and hooks.

Providers are shared runtime services that SQLBuild discovers, configures, and injects into your Python nodes and hooks. Use them for external connections, API clients, or any stateful service that multiple nodes need access to.

### Defining a provider

Create a Python file under `providers/` in your project. A provider is a class that subclasses `Provider` from `sqlbuild.providers`:

```python
# providers/warehouse_client.py
from sqlbuild.providers import Provider

class WarehouseClient(Provider):
    api_key: str
    endpoint: str = "https://api.example.com"

    def setup(self, ctx):
        self.session = create_session(self.api_key, self.endpoint)

    def teardown(self):
        self.session.close()
```

`Provider` extends [pydantic-settings `BaseSettings`](https://docs.pydantic.dev/latest/concepts/pydantic_settings/), so provider fields are validated and can be populated from environment variables automatically.

### Provider name

Each provider has a runtime name used for injection. By default, the name is derived from the class name by converting to `lower_snake_case`:

- `WarehouseClient` becomes `warehouse_client`
- `SlackNotifier` becomes `slack_notifier`

Override the name explicitly with `provider_name`:

```python
class WarehouseClient(Provider):
    provider_name = "warehouse"
    api_key: str
```

Provider names must be valid Python identifiers (`lower_snake_case`). They share the global project resource namespace with models, sources, seeds, functions, loaders, tasks, assets, checks, and hooks.

### Using providers in Python nodes

Providers are injected into Python node functions by **parameter name**. Add a parameter whose name matches the provider's runtime name:

```python
from sqlbuild.tasks import task

@task
def export_orders(ctx, warehouse_client):
    warehouse_client.session.upload(ctx.query("SELECT * FROM orders"))
```

SQLBuild matches the parameter name `warehouse_client` to the discovered provider with that name, sets it up if it hasn't been already, and passes it to the function.

You can also type-annotate the parameter for IDE support and compile-time validation:

```python
from sqlbuild.tasks import task
from providers.warehouse_client import WarehouseClient

@task
def export_orders(ctx, warehouse_client: WarehouseClient):
    warehouse_client.session.upload(ctx.query("SELECT * FROM orders"))
```

When a type annotation is present, SQLBuild validates that the discovered provider is an instance of the annotated class. A mismatch raises a compile-time error.

Provider injection works in all Python node types:

- **Loaders** (`@loader`)
- **Tasks** (`@task`)
- **Assets** (`@asset`)
- **Checks** (`@check`)

### Using providers in hooks

Python lifecycle hooks also support provider injection by parameter name:

```python
# hooks/python/notify.py
from sqlbuild.hooks import hook

@hook
def notify_complete(ctx, slack_notifier):
    slack_notifier.send(f"Model {ctx.model_name} built successfully")
```

```sql
MODEL (
  materialized table,
  post_hooks [python("notify_complete")],
);
```

Providers are also available on the `HookContext` via `ctx.providers`:

```python
@hook
def notify_complete(ctx):
    notifier = ctx.providers.slack_notifier
    notifier.send(f"Model {ctx.model_name} built successfully")
```

### Using providers via context

All Python node contexts (`TaskContext`, `AssetContext`, `CheckContext`, `LoaderContext`) and `HookContext` expose a `ctx.providers` container for name-based access:

```python
@task
def export_orders(ctx):
    client = ctx.providers.warehouse_client
    client.session.upload(ctx.query("SELECT * FROM orders"))
```

Both approaches (parameter injection and `ctx.providers`) are equivalent. Parameter injection is more explicit and enables type checking; `ctx.providers` is useful when provider access is conditional or dynamic.

### Lifecycle

Providers follow a lazy setup, reverse-teardown lifecycle scoped to the command invocation:

1. **Discovery** - on compile, SQLBuild discovers all `Provider` subclasses under `providers/` and validates their settings (from environment variables or field defaults).
2. **Lazy setup** - `setup(ctx)` is called the first time a provider is accessed during a build, not at startup. Providers that are never used are never set up.
3. **Teardown** - after the command completes, `teardown()` is called on all providers that were set up, in reverse setup order. Teardown runs even if the build failed.

```python
class WarehouseClient(Provider):
    api_key: str

    def setup(self, ctx):
        # Called once, the first time any node accesses this provider
        self.connection = connect(self.api_key)

    def teardown(self):
        # Called after the command completes
        self.connection.close()
```

Both `setup` and `teardown` are optional. A provider with only field declarations and no lifecycle methods is valid; it acts as a validated configuration object.

### Configuration from environment variables

Because `Provider` extends `pydantic-settings BaseSettings`, fields without defaults are read from environment variables. The environment variable name matches the field name in uppercase:

```python
class SlackNotifier(Provider):
    slack_token: str          # reads SLACK_TOKEN from environment
    channel: str = "#builds"  # has a default, environment variable is optional
```

See the [pydantic-settings documentation](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) for advanced configuration like custom env prefixes, `.env` file support, and nested settings.

### Discovery rules

- Provider classes are discovered from `.py` files under `providers/` recursively
- Files named `__init__.py` or starting with `_` are skipped
- Each concrete (non-abstract) subclass of `Provider` is registered
- Provider names must be globally unique across project resources
- Settings are validated at discovery time. Missing required fields (without environment variables set) raise a discovery error immediately, not at runtime

### Plan output

When providers are used by Python nodes or hooks, `sqb plan` shows a Providers section listing each provider and its consumers:

```
Providers
  warehouse_client  2 nodes
  slack_notifier    1 node
```

Use `--verbose` to see which specific nodes consume each provider.

### Project layout

```
my-project/
  providers/
    warehouse_client.py
    slack_notifier.py
  hooks/
    sql/
      record_notification.sql
    python/
      notify.py
  loaders/
    load_orders.py
  tasks/
    export_orders.py
```

## SQL References

Source: `concepts/python-nodes/sql-references.mdx`

Read SQL models and sources from Python nodes without creating SQL dependencies.

Python nodes can **read** SQL models and sources at runtime, but they cannot depend on them as graph edges (see the [SQL boundary](/concepts/python-nodes/overview#the-sql-boundary)). Typed references make this read-only access explicit and safe across direct and virtual modes.

### Declaring a reference

Use `model()` and `source()` from `sqlbuild.refs` in a node's `depends_on`:

```python
from sqlbuild.refs import model, source
from sqlbuild.tasks import task

@task(depends_on=model("fact_orders"))
def export_orders(ctx):
    ...

@task(depends_on=source("raw_orders"))
def inspect_raw(ctx):
    ...
```

Declaring the reference does two things:

1. It tells SQLBuild the node reads that SQL resource, so the node is scheduled **after** the resource is built (read-side).
2. It authorizes `ctx.relation(...)` to resolve that reference at runtime.

It does **not** make the SQL resource depend on the Python node. The dependency is one-way: Python reads SQL, never the reverse.

### Resolving with ctx.relation

Always resolve a reference to its concrete relation with `ctx.relation(...)` instead of hardcoding the table name:

```python
@task(depends_on=model("fact_orders"))
def export_orders(ctx):
    relation = ctx.relation(model("fact_orders"))
    rows = ctx.query(f"SELECT * FROM {relation}").fetchall()
    return ctx.result(metadata={"rows": len(rows)})
```

`ctx.relation(...)` returns the adapter-qualified relation name for the current run. Passing a reference that was not declared in `depends_on` raises an error.

Do not hardcode model or source names in raw SQL. In virtual mode a model resolves to a versioned VDE relation (for example `marts__feature_x.fact_orders`), not the bare name. A query like `ctx.query("SELECT * FROM fact_orders")` will fail or read the wrong relation. Always use `ctx.relation(model("fact_orders"))`.

### model vs source

| Reference | Resolves to |
|-----------|-------------|
| `model("name")` | The built model relation (the VDE logical relation in virtual mode) |
| `source("name")` | The source read relation, following deferred-source semantics |

`source(...)` respects `defer_sources_to`, so a node reading a source in `dev` can read the deferred target's data just like SQL models do.

### Where references are allowed

- **Tasks** and **assets** may declare `model()` and `source()` references and read them with `ctx.relation(...)`.
- **Checks** may not reference SQL resources. Validate SQL with [audits](/concepts/audits).
- A Python node referencing a SQL resource never turns into a SQL dependency; selector expansion will not pull Python outputs into SQL model dependencies.

## Overview

Source: `concepts/virtual-environments.mdx`

Version-controlled SQL pipeline environments with instant promotion and rollback.

Virtual environments are in alpha. The core workflow (build, promote, rollback, reconcile) is functional and tested across supported adapters. The API and CLI surface may evolve based on feedback. Do not use virtual environments for production workloads yet.

Virtual environments (VDEs) let you build, preview, and promote SQL pipeline changes without recomputing models. Each VDE is a set of pointers to versioned physical relations. Creating a new VDE is instant (pointer copy, no data duplication), and promoting one VDE into another is a view swap, not a rebuild.

### When to use virtual environments

- **PR preview environments** - build a VDE per pull request against a production warehouse, validate with audits and tests, then promote the built versions to production without rebuilding
- **Blue/green deployments** - build into a staging VDE, promote to production atomically
- **Multi-developer isolation** - each developer works in their own VDE without conflicting with others, sharing physical versions when code is identical
- **Instant rollback** - revert production to a prior finalized state by restoring a checkpoint's pointer set

Virtual environments are opt-in via `virtual_environments = true` (under `[settings]`) and require a state store. Projects that don't need environment isolation or promotion workflows should use the default direct mode.

### How it works

#### Targets and virtual environments

In virtual mode there are two separate concepts:

**Targets** are the existing SQLBuild build contexts from `sqlbuild_project.toml` (e.g. `dev`, `prod`). They choose the warehouse connection, schema, and state database. In virtual mode they are sometimes called *physical targets* to distinguish them from VDEs.

**Virtual data environments (VDEs)** are versioned pointer sets stored in the state database. They choose which model versions the logical views point to.

```bash
sqb --target prod build --virtual-env pr_123
```

This means: use the `prod` physical target (warehouse, state DB), but build into the `pr_123` virtual environment.

#### Version identity

Model versions are identified by content hashes, not sequence numbers. The hash includes the model's query SQL, version-identity config, and upstream version hashes. If two developers compile identical code with identical upstream versions, they get the same hash and reuse the same physical relation. No data is duplicated.

#### Physical and logical relations

Virtual mode creates two types of warehouse objects:

- **Physical version relations** store actual data: `<schema>__sqb_physical.<model>__v_<hash>`
- **Logical VDE views** point to physical versions: `<schema>__<vde_name>.<model>` as `SELECT * FROM <physical_version>`

Users query the logical views. SQLBuild manages the physical layer.

#### Zero-copy branching

Creating a new VDE from a baseline copies only pointer rows in the state database, not data. Unchanged models share the same physical relations across VDEs.

#### Instant promotion

Promoting VDE `pr_123` to `prod` updates the pointer rows and refreshes the logical views. No models are rebuilt. If every model in the source VDE has already been built and validated, promotion is a metadata operation.

### Try it

```bash
sqb playground --template virtual
cd sqlbuild-playground
sqb state init
sqb build
sqb build --virtual-env pr
sqb diff dev:pr --schema-only --allow-partial-diff
sqb promote --from pr --to dev
sqb state checkpoints list
sqb rollback
```

This creates a self-contained DuckDB project with loaders, models, tests, scenarios, and a local state store. No warehouse credentials required.

### Example workflow

```bash
# Initialize state store
sqb state init

# First build creates physical versions and default VDE
sqb build

# Create a PR preview VDE
sqb build --virtual-env pr_123

# Modify a model, rebuild in the PR VDE
sqb build --virtual-env pr_123

# Compare VDEs
sqb diff dev:pr_123

# Promote PR versions to the default VDE
sqb promote --from pr_123 --to dev
```

### What's next

- [Setup](/concepts/virtual-environments/setup) - configuration and state initialization
- [Building](/concepts/virtual-environments/building) - virtual builds, partial builds, seeded incrementals
- [Promotion](/concepts/virtual-environments/promotion) - promoting VDEs
- [Rollback](/concepts/virtual-environments/rollback) - checkpoints and rollback
- [Clone](/concepts/virtual-environments/clone) - hydrating physical versions from a source warehouse
- [Diff](/concepts/virtual-environments/diff) - comparing VDE ref sets
- [Adopt and Detach](/concepts/virtual-environments/adopt-detach) - migrating existing projects
- [Reconcile](/concepts/virtual-environments/reconcile) - diagnosing and repairing drift
- [Locks](/concepts/virtual-environments/locks) - concurrent access control
- [Janitor](/concepts/virtual-environments/janitor) - cleanup and retention
- [Recovery](/concepts/virtual-environments/recovery) - what to do when things break

## Setup

Source: `concepts/virtual-environments/setup.mdx`

Configure virtual environments and initialize the state store.

Virtual environments require two things: `virtual_environments = true` in your project settings, and a state store configured for your active target.

### Project configuration

```toml
name = "my_project"
adapter = "duckdb"
default_target = "dev"

[settings]
virtual_environments = true

[connections.local]
database = "warehouse.duckdb"

[targets.dev]
connection = "local"
schema = "dev"

[targets.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"

[targets.dev.state.connection]
database = "state.duckdb"
```

The `virtual_environments` setting switches the project from direct mode (default) to virtual mode. All state, plan, build, promote, rollback, and reconcile commands route through the virtual path when this is enabled.

### State configuration

Each physical target that uses virtual mode needs a `[targets.<name>.state]` block:

| Field | Required | Description |
|-------|----------|-------------|
| `backend` | Yes | State store engine: `duckdb` or `postgres` |
| `schema` | Yes | Schema name for state tables |
| `connection` | Yes | Backend-specific connection config |
| `allow_reset` | No | Whether `sqb state reset` is permitted (default: `false`) |
| `unsuffixed_virtual_env` | No | VDE name that uses the base schema without a suffix (for [adopt/detach](/concepts/virtual-environments/adopt-detach)) |

#### DuckDB state backend

```toml
[targets.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"

[targets.dev.state.connection]
database = "state.duckdb"
```

DuckDB state stores are file-based. Relative paths are resolved against the project directory. Suitable for local development and single-user workflows. Not recommended when multiple processes or CI jobs need concurrent state access.

#### Postgres state backend

```toml
[targets.prod.state]
backend = "postgres"
schema = "sqlbuild_state"

[targets.prod.state.connection]
host = "state-db.internal"
port = 5432
user = "sqlbuild_state"
password = "${ENV:STATE_DB_PASSWORD}"
dbname = "sqlbuild_state"
```

Postgres is recommended for production. It supports concurrent access from multiple developers or CI jobs.

### State initialization

Before using virtual commands, initialize the state store:

```bash
sqb state init
```

This creates the state tables in the configured schema. Run it once per physical target.

### State lifecycle

| Command | Description |
|---------|-------------|
| `sqb state init` | Create state tables |
| `sqb state migrate` | Back up current state and re-initialize tables |
| `sqb state rollback` | Restore from the latest backup |
| `sqb state rollback --backup-id <id>` | Restore from a specific backup |
| `sqb state reset --auto-approve` | Drop all state tables (requires `allow_reset = true`) |

`state migrate` creates a backup schema (e.g. `sqlbuild_state__backup_<id>`) before re-initializing. This lets you roll back if a migration causes problems.

`state reset` is destructive and requires both `allow_reset = true` in config and `--auto-approve` on the command line.

### Local overrides

Use `sqlbuild_local.toml` to override state connection config per developer:

```toml
[targets.dev.state.connection]
database = "local-state.duckdb"
```

This is useful when each developer uses a local state file while the project config points to a shared state database.

### Per-target state

Different physical targets can use different state backends:

```toml
[targets.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"

[targets.dev.state.connection]
database = "state.duckdb"

[targets.prod.state]
backend = "postgres"
schema = "sqlbuild_state"

[targets.prod.state.connection]
host = "prod-state.internal"
dbname = "sqlbuild_state"
```

Each physical target has its own state store. VDEs are scoped to their physical target and cannot be promoted or compared across different physical targets.

### Unsuffixed VDE naming

By default, all VDE logical views use a suffixed schema: `dev__kevin.fact_orders`. For the primary VDE that consumers query directly (e.g. the production VDE), you typically want clean unsuffixed names: `dev.fact_orders`.

Configure this with `unsuffixed_virtual_env`:

```toml
[targets.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"
unsuffixed_virtual_env = "dev"

[targets.dev.state.connection]
database = "state.duckdb"
```

With this config, VDE `dev` uses `dev.fact_orders` while other VDEs like `kevin` use `dev__kevin.fact_orders`.

This setting is also required for [adopt and detach](/concepts/virtual-environments/adopt-detach) operations so that existing consumer queries continue to work after migrating to virtual mode.

### Janitor configuration

When using virtual environments, configure the janitor to run periodically to clean up expired VDEs, old checkpoints, and unreferenced physical versions:

```toml
[janitor]
enabled = true
retention_days = 30
max_checkpoints = 20
```

See [Janitor](/concepts/virtual-environments/janitor) for details on what gets cleaned up and how retention works.

### State tables

The state store contains current-state tables and append-only history tables. You do not need to interact with these directly, but understanding what is stored helps when debugging:

**Current state:** `state_versions`, `model_versions`, `function_versions`, `physical_relations`, `physical_relation_ancestry`, `virtual_environments`, `virtual_environment_refs`, `virtual_environment_function_refs`, `virtual_environment_checkpoints`, `virtual_environment_checkpoint_refs`, `virtual_environment_checkpoint_function_refs`, `locks`, `state_operations`

**History:** `plan_runs`, `virtual_environment_ref_events`, `reconcile_events`, `state_migration_events`, `state_operation_events`

## Building

Source: `concepts/virtual-environments/building.mdx`

Virtual builds, VDE creation, partial builds, and seeded incrementals.

Virtual builds create versioned physical relations and update VDE pointer sets. The build lifecycle is the same as direct mode (seeds, tests, models, audits), but model outputs are written to versioned physical tables and exposed through logical VDE views.

Virtual builds run ingress (loaders and Python nodes that feed sources) as a separate phase before SQL model execution. This means independent SQL models that do not depend on loaders will wait for all ingress to complete before starting. Direct mode does not have this limitation. This keeps VDE state persistence simpler and safer but may add wall time when ingress is slow and independent SQL work is available. A future optimization may allow overlapping ingress with independent SQL execution.

### Default VDE

When you run `sqb build` in virtual mode without `--virtual-env`, the VDE name defaults to the active physical target name:

```bash
sqb build
```

If the active environment is `dev`, this builds into VDE `dev`. On first run, it creates physical version relations and logical VDE views for all models.

### Explicit VDE

Use `--virtual-env` to build into a named VDE:

```bash
sqb build --virtual-env pr_123
```

If VDE `pr_123` does not exist, SQLBuild creates it by inheriting refs from the baseline VDE (the default VDE for the active physical target). Unchanged models share the same physical relations as the baseline - no data is copied.

Only models with changed code, config, or upstream versions get new physical version relations.

### Physical naming

Physical version relations are stored in a dedicated schema:

```
<base_schema>__sqb_physical.<model_name>__v_<hash>
```

For example: `dev__sqb_physical.fact_orders__v_8f3a9c12`

Logical VDE views are created in a VDE-suffixed schema:

```
<base_schema>__<vde_name>.<model_name>
```

For example: `dev__pr_123.fact_orders`

When `unsuffixed_virtual_env` is configured, the named VDE uses the base schema directly:

```
dev.fact_orders
```

### VDE status

| Status | Meaning |
|--------|---------|
| `finalized` | All models match their expected version hashes. The VDE is coherent and eligible for promotion. |
| `active` | Some models are stale (partial build or pending changes). The VDE is a work in progress. |
| `detached` | The VDE has been detached via `sqb state detach`. Build, promote, and rollback are blocked. |

### Partial builds

Build a subset of models with `--select`:

```bash
sqb build --virtual-env pr_123 --select fact_orders
```

Partial builds leave the VDE in `active` (working) status if downstream models remain stale. A follow-up `sqb build --virtual-env pr_123 --changes-only` (without `--select`) builds the remaining stale models to finalize the VDE; a plain `sqb build --virtual-env pr_123` rebuilds the whole selection.

#### Stale upstream coherence

If a selected model has stale required upstream models, the build blocks by default:

```bash
sqb build --virtual-env pr_123 --select fact_orders
# error: selected models have stale required upstreams: stg_orders
```

Pass `--include-stale-upstreams` to expand the selection to the minimal set of stale ancestor models needed to make the selected scope coherent:

```bash
sqb build --virtual-env pr_123 --select fact_orders --include-stale-upstreams
```

#### Stale-driven selection

Virtual environment builds run the full selection by default, like direct mode. Add `--changes-only` to intersect the selection with the stale-driven set, so only models that are both selected and stale are built:

```bash
sqb build --virtual-env pr_123 --select path:models/marts --changes-only
```

This is useful when the stale cascade is large and you want to build a coherent subgraph without running unchanged models. Without `--changes-only`, every selected model is built regardless of state.

Change-aware pruning is opt-in within virtual environments and unavailable in direct mode. See [Planning and Change Detection](/concepts/planning) for how fingerprints, source freshness, and identity tracking determine what gets built.

### Stale detection

SQLBuild determines which models and seeds need rebuilding by comparing expected version hashes against bound version hashes in the VDE refs:

1. **Expected local hash** - derived from the node's query SQL (for models), content hash (for seeds), version-identity config, and source freshness hashes
2. **Expected version hash** - local hash propagated through upstream dependencies (upstream hash changes cascade downstream)
3. **Bound version hash** - the hash currently stored in the VDE refs from the last successful build

A node is stale when `bound != expected`. Stale nodes whose own local hash changed are roots (`query changed`, `config changed`, `function changed`). Others are stale due to `upstream changed`.

Seeds participate in version identity the same way as models. They are loaded into versioned physical tables with logical VDE views on top, and their version hashes and refs are tracked per virtual environment in the state backend. Unchanged seeds are not reloaded.

Source freshness observations and Python node identities are also persisted per virtual environment and included in version hash computation. When a source's observed data version changes, its downstream models become stale. See [Sources: Source freshness](/concepts/sources#source-freshness) for configuration.

### Seeded incremental builds

When an incremental model's version hash changes, SQLBuild seeds the new physical version from the prior physical version before running the incremental delta. This avoids full rebuilds of large incremental tables.

| Adapter | Seed strategy |
|---------|--------------|
| Snowflake | Zero-copy clone |
| BigQuery | Table clone |
| Databricks | Deep clone |
| DuckDB, Postgres, SQL Server | CTAS copy |

For append models with bounded replay (`replay_on_change bounded-7d`), the seed copies only rows before the replay window cutoff. The incremental delta then appends the bounded range without duplicating rows.

### Custom materializations

Custom materializations are supported in virtual mode. By default, SQLBuild seeds new physical versions using the direct clone/copy strategy before calling the custom `materialize` function.

For custom materializations that need different seeding behavior, define a `prepare_version` function alongside `materialize`:

```python
from sqlbuild.virtual.executor.models import VersionPrepareContext
from sqlbuild.executor.custom.models import MaterializationContext, MaterializationResult

def prepare_version(ctx: VersionPrepareContext) -> None:
    """Prepare the new physical destination from the prior version."""
    ctx.execute_sql(f"CREATE TABLE {ctx.destination} AS SELECT * FROM {ctx.prior_relation}")

def materialize(ctx: MaterializationContext) -> MaterializationResult:
    """Run the custom materialization logic against the prepared destination."""
    ...
```

If `prepare_version` is not defined, the framework uses the default clone/copy. Most custom materializations do not need to define it.

`VersionPrepareContext` provides `prior_relation` (the source physical version), `destination` (the new physical destination relation), `adapter`, `connection`, `execute_sql()`, `config`, and `vars`.

Custom materializations in virtual mode must write only to `ctx.destination`. Side-effect writes to other relations are not tracked by virtual state, not cleaned up by janitor, and not restored by rollback.

### Functions

Functions are published into the logical VDE schema, not the physical layer. Each VDE has its own copy of function definitions. Function versions are tracked in state and participate in promotion and rollback.

### Plan

Use `sqb plan` to preview what a virtual build would do without executing:

```bash
sqb plan
sqb plan --virtual-env pr_123
sqb plan --select fact_orders
```

Virtual plan output shows:
- Virtual environment name and status (finalized/working)
- Stale root count and root set
- Stale model count
- Query diffs from prior bound versions
- Remaining stale models after partial selection

## Promotion

Source: `concepts/virtual-environments/promotion.mdx`

Promote VDE refs and diff virtual environments.

Promotion copies model version refs from one VDE to another and refreshes the target's logical views. No models are rebuilt - it is a pointer swap.

### Basic usage

```bash
sqb promote --from pr_123 --to dev
```

This updates VDE `dev` to point at the same physical versions that VDE `pr_123` uses. The target's logical views (`dev__dev.*` or `dev.*` if unsuffixed) are refreshed to point at the promoted physical relations.

### What happens during promotion

1. Target VDE lock is acquired
2. Source VDE is validated (finalized, current with workspace)
3. Source model refs are copied to target VDE refs
4. Source function refs are copied and function definitions are republished in the target schema
5. Target logical VDE views are refreshed
6. A checkpoint is created if the target is finalized
7. Target VDE lock is released

### Partial promotion

Promote a subset of models with `--select`:

```bash
sqb promote --from pr_123 --to dev --select fact_orders
```

Partial promotion can leave the target VDE with stale downstream models - models that still point at older versions than the promoted scope expects. When this happens, promotion is blocked by default so you don't accidentally leave the target in a working state.

To accept a working target, pass `--allow-partial-promotion`:

```bash
sqb promote --from pr_123 --to dev --select fact_orders --allow-partial-promotion
```

The target VDE is marked `working` after the promotion. You can finalize it later by promoting or building the remaining models.

If the models you select depend on upstream models that are themselves stale in the source, the promoted scope would not be coherent on its own. Pass `--include-stale-upstreams` to expand the selection to include the minimal set of required upstream models:

```bash
sqb promote --from pr_123 --to dev --select fact_orders --include-stale-upstreams
```

### Source VDE requirements

**Whole promotion** requires the source VDE to be finalized and current with the workspace (no stale models vs current code). If the source VDE has been built but the code has since changed, you need to rebuild the source VDE first or use partial promotion.

**Partial promotion** does not require a finalized source. A working source VDE is allowed when using `--select` for a coherent scope.

### Guards

| Condition | Behavior |
|-----------|----------|
| Source VDE not finalized (whole promotion) | Blocks. Use `--select` for partial promotion from a working source. |
| Source VDE has stale models vs workspace | Blocks. Rebuild the source VDE or use `--select`. |
| Target VDE is locked | Blocks. Wait or clear the lock with `sqb state locks clear`. |
| Target VDE is detached | Blocks. Detached VDEs cannot be promoted to. |
| Source VDE is detached | Blocks. Detached VDEs cannot be promoted from. |
| Partial promotion leaves target working | Blocks unless `--allow-partial-promotion` is set. |

### Comparing VDEs before promotion

Use `sqb diff` to compare VDE ref sets before promoting. See [Diff](/concepts/virtual-environments/diff) for details.

## Rollback

Source: `concepts/virtual-environments/rollback.mdx`

Checkpoints and rollback for virtual environments.

Rollback restores a VDE to a prior finalized state by rebinding its refs to a stored checkpoint.

### Checkpoints

Checkpoints are created automatically when a VDE reaches `finalized` status:

- After a whole build where all models match expected versions
- After a whole promotion where the target VDE is finalized

Each checkpoint stores the complete set of model refs and function refs for that VDE at that point in time. Checkpoints are retained according to `[janitor] max_checkpoints` (default: 20).

### Basic rollback

Restore the previous finalized checkpoint for the default VDE:

```bash
sqb rollback
```

For an explicit VDE:

```bash
sqb rollback --virtual-env pr_123
```

### Explicit checkpoint

Restore a specific checkpoint:

```bash
sqb rollback --checkpoint-id <id>
```

Use `sqb state checkpoints list` to see available checkpoints.

### What happens during rollback

1. Target VDE lock is acquired
2. The target checkpoint is located (previous finalized by default, or explicit id)
3. Checkpoint physical relations are validated to still exist in the warehouse
4. VDE refs are replaced with the checkpoint's ref set
5. VDE function refs are replaced with the checkpoint's function ref set
6. Logical VDE views are refreshed to point at the restored physical versions
7. Function definitions are republished from the checkpoint's function versions
8. Target VDE lock is released

### Partial rollback

Roll back a subset of models with `--select`:

```bash
sqb rollback --select fact_orders
```

Rolling back some models but not others can leave the VDE with stale models - models whose restored versions no longer line up with the rest of the VDE. When this happens, rollback is blocked by default so you don't leave the VDE in a working state by accident.

To accept a working VDE, pass `--allow-partial-rollback`:

```bash
sqb rollback --select fact_orders --allow-partial-rollback
```

The VDE is marked `working` after the rollback. You can finalize it later by building or rolling back the remaining models.

If the models you select depend on upstream models that also need to be restored for the scope to be coherent, pass `--include-stale-upstreams` to expand the selection to the minimal set of required upstream refs from the checkpoint:

```bash
sqb rollback --select fact_orders --include-stale-upstreams
```

### Guards

| Condition | Behavior |
|-----------|----------|
| No previous checkpoint exists | Blocks. Build the VDE first to create a finalized checkpoint. |
| Checkpoint physical relations deleted | Blocks. The physical version tables have been cleaned up by janitor. Use a more recent checkpoint or rebuild. |
| Unknown checkpoint id | Blocks with error. |
| Target VDE is locked | Blocks. Wait or clear the lock. |
| Target VDE is detached | Blocks. Detached VDEs cannot be rolled back. |
| Partial rollback leaves VDE working | Blocks unless `--allow-partial-rollback` is set. |

### Checkpoint inspection

List checkpoints for a VDE:

```bash
sqb state checkpoints list
sqb state checkpoints list --virtual-env pr_123
```

Show a checkpoint's model refs:

```bash
sqb state checkpoints show <checkpoint_id>
```

Diff current VDE refs against a checkpoint:

```bash
sqb state checkpoints diff <checkpoint_id>
```

## Adopt and Detach

Source: `concepts/virtual-environments/adopt-detach.mdx`

Migrate existing projects to and from virtual mode.

Adopt converts an existing stateless project into virtual mode. Detach reverses the process. Both are interactive operations that require typed confirmation.

### Adopt

`sqb state adopt` takes existing warehouse relations (tables and views) and converts them into versioned physical relations with VDE views at the original names.

#### Prerequisites

1. State store must be initialized (`sqb state init`)
2. `unsuffixed_virtual_env` must be configured so existing object names are preserved:

```toml
[targets.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"
unsuffixed_virtual_env = "dev"

[targets.dev.state.connection]
database = "state.duckdb"
```

Without `unsuffixed_virtual_env`, adopt blocks with a config error. This is intentional - without it, existing relations would be renamed to suffixed schemas (e.g. `dev__dev.fact_orders`), breaking existing consumers.

#### What happens

1. For each model, the existing table is moved/renamed into the physical schema (`dev__sqb_physical.fact_orders__v_<hash>`)
2. A logical VDE view is created at the original name (`dev.fact_orders`) pointing to the physical version
3. Model versions, physical relations, VDE record, and VDE refs are persisted in state

#### Usage

```bash
sqb state adopt --allow-copy
```

The command prints an adoption plan and requires typed confirmation:

```
Type "adopt dev" to confirm: adopt dev
```

`--allow-copy` is required when the adapter does not support native same-schema rename (cross-schema moves, some adapters). Without it, adopt blocks with `requires --allow-copy` if a copy fallback would be needed.

#### View models

View models are adopted the same way - a versioned physical view is created in the physical schema, and the original name becomes a logical VDE view.

### Detach

`sqb state detach` reverses adoption, collapsing a VDE back into normal stateless relations.

#### Prerequisites

The VDE must be `finalized`. If the VDE is working (has stale models), detach blocks:

```
error: detach requires a finalized virtual environment
```

Build the VDE to finalize it first, or resolve any pending changes.

#### What happens

1. For each table model, the physical version is moved/renamed back to the original target name
2. For each view model, the view is recreated from compiled SQL at the original target name (not copied from the physical ref)
3. The VDE is marked `detached` in state
4. VDE refs are preserved for audit/recovery and janitor protection

#### Usage

```bash
sqb state detach --allow-copy
```

Requires typed confirmation:

```
Type "detach dev" to confirm: detach dev
```

#### After detach

A detached VDE is blocked from further virtual operations:

- `sqb build` blocks with "virtual environment is detached"
- `sqb promote --from <detached>` or `--to <detached>` blocks
- `sqb rollback` on a detached VDE blocks

The project can continue operating in direct mode, or you can re-adopt to return to virtual mode.

#### Detached VDE cleanup

Detached VDE refs and state rows are cleaned up by the [janitor](/concepts/virtual-environments/janitor), not by detach itself. This preserves refs for recovery if detach fails partway through.

### Interrupted operations

Adopt and detach are multi-step warehouse operations that cannot be wrapped in a single transaction. If an operation fails partway through:

- A `failed` operation record is persisted in state with the error message
- VDE refs and checkpoints remain intact
- The warehouse may have partial artifacts (e.g. table moved to physical schema but view not yet created)

Recovery path:

1. Run `sqb reconcile` to diagnose the current state
2. Use `sqb reconcile repair-view` or manual warehouse repair as needed
3. Retry the adopt or detach operation

There is no automatic resume command. SQLBuild records the failure state and leaves recovery to the operator.

## Clone

Source: `concepts/virtual-environments/clone.mdx`

Hydrate physical versions from a source warehouse.

In virtual mode, `sqb clone` hydrates physical version relations from a source warehouse into the target physical storage layer. It does not copy VDE pointer sets or create logical views - it copies the underlying physical data so that builds and promotions can reference those versions locally.

This is useful for seeding a new target from an existing one, or restoring physical versions that were cleaned up by the janitor.

As in direct mode, `--from` selects an origin namespace and clone-origin policy, not a
connection. `--to` (or the active target) supplies the only physical connection. The origin
physical namespace must be readable through that destination connection; SQLBuild never opens
the origin target connection or transfers data across accounts, servers, or files using a
second connection.

### How it works

Virtual clone looks up expected physical version relations in the source warehouse by their naming convention (`<schema>__sqb_physical.<model>__v_<hash>`) and copies them into the target warehouse. It then registers the copied relations in the target state store.

Target VDE refs and logical views are not changed. Clone only populates the physical layer.

### Default mode

Without `--virtual-env`, clone hydrates physical versions matching the current workspace's expected fingerprints:

```bash
sqb clone --from prod --to dev
```

This computes expected version hashes from the current code, looks for matching physical relations in the source warehouse, and copies them into the target.

### VDE ref mode

With `--virtual-env`, clone hydrates physical versions referenced by a specific VDE in the target state store:

```bash
sqb clone --from prod --to dev --virtual-env pr_123
```

This reads VDE `pr_123`'s refs from the target state, looks for those physical relations in the source warehouse, and copies them into the target. Useful when a VDE's physical versions have been deleted (by janitor or manual cleanup) but the state refs still exist.

### Selection

Scope which models are hydrated:

```bash
sqb clone --from prod --to dev --select fact_orders
```

### Missing source artifacts

If a source physical relation does not exist, clone reports it as missing and continues with the remaining models. The exit code is non-zero if any models are missing.

### Model version locks

If a target model version is locked (another process is building that version), clone blocks by default:

```bash
# Skip locked versions and hydrate the rest
sqb clone --from prod --to dev --skip-locked
```

### What clone does not do

- Does not create or update VDE refs
- Does not create or refresh logical VDE views
- Does not read the source state database (it uses warehouse-level artifact discovery)
- Does not change the target VDE status

Clone is a physical-layer operation. VDE pointer management is handled by [build](/concepts/virtual-environments/building) and [promote](/concepts/virtual-environments/promotion).

### Comparison with direct-mode clone

In direct mode, `sqb clone` copies model relations between targets using zero-copy cloning where supported. In virtual mode, clone hydrates versioned physical relations instead. The source and target are still physical targets, but the copied objects are physical version relations rather than normal model targets.

## Diff

Source: `concepts/virtual-environments/diff.mdx`

Compare virtual data environments.

In virtual mode, `sqb diff` compares VDE ref sets within the same physical target. It shows which models have different version hashes and, for changed models, reports schema and row-level differences.

### Basic usage

```bash
sqb diff dev:pr_123
```

The format is `<left_vde>:<right_vde>`. Both VDEs must exist in the active physical target's state store.

### What diff shows

1. **Ref comparison** - which models have different version hashes between the two VDEs
2. **Schema differences** - column additions, removals, and type changes for changed models
3. **Row differences** - row counts, matched/unmatched rows, and changed column values

Identical refs are skipped by default so the output focuses on models that actually differ. A model with a different version hash is included in the comparison even if its resulting data happens to be identical.

### Options

```bash
# Schema differences only (no row comparison)
sqb diff dev:pr_123 --schema-only

# Full row-level comparison
sqb diff dev:pr_123 --full

# Compare specific models
sqb diff dev:pr_123 --select fact_orders

# No color output
sqb --no-color diff dev:pr_123
```

### Working VDE guard

If either VDE is working (has stale models that haven't been built yet), diff is blocked by default because the comparison may be incomplete:

```bash
# Blocked
sqb diff dev:pr_123

# Allowed with explicit override
sqb diff dev:pr_123 --allow-partial-diff
```

This guard prevents misleading diff output when one VDE has pending changes that haven't been materialized yet.

### Comparison with direct-mode diff

In direct mode, `sqb diff prod:dev` compares physical target schemas and data directly in the warehouse. In virtual mode, `sqb diff dev:pr_123` compares VDE pointer sets within a single physical target, then inspects the physical versions those pointers reference.

The output format is the same - schema diffs, row counts, changed columns, and example rows. The difference is what is being compared: physical targets vs virtual pointer sets.

## Reconcile

Source: `concepts/virtual-environments/reconcile.mdx`

Diagnose and repair drift between state and warehouse.

Reconcile detects and repairs inconsistencies between the virtual state store and the actual warehouse objects.

### Report

Run reconcile without a subcommand to get a diagnostic report:

```bash
sqb reconcile --virtual-env dev
```

This inspects the VDE's refs, checks that logical views exist and point to the expected physical relations, and reports any issues without changing anything.

### Repair view

Recreate a logical VDE view from trusted state:

```bash
sqb reconcile repair-view --virtual-env dev --model fact_orders
```

This runs `CREATE OR REPLACE VIEW` for the logical VDE view, pointing it at the physical version relation recorded in the VDE's refs. It is idempotent - running it when the view is already correct is a no-op.

#### Guards

| Condition | Behavior |
|-----------|----------|
| Logical target is a table (not a view) | Blocks. Drop the table manually first, then retry. |
| Physical relation is missing | Blocks. Rebuild the model with `sqb build --select <model>`. |
| Target VDE is locked | Blocks. Wait or clear the lock. |

No confirmation is needed. The command is explicit and idempotent.

### Attach

Rebind a VDE model ref to a different tracked physical relation:

```bash
sqb reconcile attach --virtual-env dev --model fact_orders \
  --physical-relation dev__sqb_physical.fact_orders__v_8f3a9c12
```

This updates the VDE ref for `fact_orders` to point at the specified physical relation and refreshes the logical view.

#### Guards

| Condition | Behavior |
|-----------|----------|
| Physical relation not tracked in state | Blocks. Only physical relations registered in SQLBuild state can be attached. |
| Physical relation tracked for a different model | Blocks. Cannot attach a relation that belongs to another model. |
| Logical target is a table (not a view) | Blocks. |
| Target VDE is locked | Blocks. |
| Wrong confirmation | Blocks. Refs remain unchanged. |

Attach requires confirmation by default. Type the confirmation text when prompted, or cancel to leave refs unchanged.

### When to use reconcile

- **Missing logical views** after a failed build, promotion, or detach - use `repair-view`
- **Wrong physical version** if a VDE ref was corrupted or you need to manually override which version a model points to - use `attach`
- **Diagnostic inspection** before or after recovery operations - use the default report

Reconcile records events in the `reconcile_events` state table for audit trail.

### Limitations

Reconcile repairs pointer/view state. It does not rebuild physical versions. If a physical relation is missing from the warehouse, the only remedy is rebuilding the model with `sqb build --select <model>`.

## Locks

Source: `concepts/virtual-environments/locks.mdx`

Advisory locks for concurrent access control.

Virtual mode uses advisory locks with TTL to prevent concurrent operations from conflicting. Locks are stored in the state database and are scoped to specific resources.

### Lock types

| Lock key | Protects | Acquired by |
|----------|----------|-------------|
| `virtual_env:<name>` | VDE pointer set and views | build, promote, rollback, reconcile, adopt, detach |
| `model_version:<model>:<hash>` | Physical version creation | build (per model version) |
| `state_migration` | State schema changes | state init, migrate, rollback, reset |

Different VDEs can be locked concurrently. Two builds targeting different VDEs do not block each other.

### Lock behavior

- Locks have an expiry time (`expires_at`). Active locks are those where `expires_at > now`.
- When a lock is successfully released, the lock row is deleted.
- Acquiring a lock over an expired lock replaces it.
- Owner identity is checked on release - only the owner that acquired the lock can release it.

### When locks block

If a lock is active and an operation requires it, the operation fails immediately with a clear error:

```
error[S014]: virtual environment 'dev' is locked
```

The operation does not wait or retry. This is intentional - SQLBuild does not implement lock queuing. If a lock is active, either wait for the holding operation to complete or clear the lock manually.

### Inspecting locks

List active locks:

```bash
sqb state locks
```

### Clearing stuck locks

If a process crashed while holding a lock, the lock may remain active until it expires. To clear it immediately:

```bash
sqb state locks clear virtual_env:dev --force
```

Only clear locks when you are certain the holding operation is no longer running. Clearing a lock while the operation is still active can cause state corruption.

### Lock expiry

Locks are acquired with a TTL (typically 10 minutes for VDE locks). If an operation takes longer than the TTL, the lock expires and another operation can acquire it. This is a safety net against abandoned locks, not a normal operating condition.

If operations consistently exceed the lock TTL, the TTL may need to be increased in a future configuration option.

## Janitor

Source: `concepts/virtual-environments/janitor.mdx`

Cleanup of virtual environment artifacts and retention policies.

The janitor manages cleanup of virtual mode artifacts: expired VDEs, old checkpoints, unreferenced physical versions, stale state backups, and expired locks. All cleanup runs through `sqb janitor` with preview and confirmation.

### Physical version protection

Physical version relations are never deleted while referenced by:

- Any active (non-detached) VDE's current refs
- Any retained checkpoint's refs

The janitor resolves the complete set of protected physical relations before considering any deletions.

### Checkpoint retention

Checkpoints are retained according to `[janitor] max_checkpoints` (default: 20):

```toml
[janitor]
max_checkpoints = 20
```

Values below 1 are rejected. Checkpoint creation never prunes history - pruning is janitor-only, behind preview and confirmation.

When old checkpoints are pruned, physical versions that were protected only by those checkpoints become eligible for deletion in the same janitor run (if not protected by active VDE refs or remaining checkpoints).

### Expired VDE cleanup

Non-active, non-detached VDEs older than `[janitor] retention_days` are pruned:

```toml
[janitor]
retention_days = 30
```

Active/default VDEs are always protected. This catches abandoned PR preview VDEs that were never promoted or cleaned up.

### Detached VDE cleanup

Detached VDEs (created by `sqb state detach`) are eligible for cleanup after `retention_days`:

- `retention_days = 0` makes them eligible immediately
- Refs, function refs, and VDE row are deleted
- Checkpoint rows remain governed by checkpoint retention
- Physical versions newly unprotected by removed refs can be deleted in the same run

Active VDE refs continue to protect physical versions even when detached refs are pruned.

### State cleanup

The janitor also prunes state-only artifacts:

- **Migration backups**: old backup schemas are deleted, but the latest backup is always preserved
- **Expired locks**: lock rows with `expires_at` in the past are deleted; active locks are never touched

### Execution order

The janitor drops warehouse physical versions before pruning state rows. If a warehouse drop fails, the corresponding state refs are preserved so the janitor can retry on the next run.

### Usage

```bash
# Preview what would be cleaned
sqb janitor

# Execute cleanup with confirmation
sqb janitor --auto-approve
```

The janitor shows a preview of all candidates (checkpoints, VDEs, physical versions, state items) and requires confirmation before executing any destructive operations.

## Recovery

Source: `concepts/virtual-environments/recovery.mdx`

Diagnosing and recovering from failures in virtual mode.

Virtual mode has explicit recovery paths for common failure scenarios. SQLBuild blocks cleanly rather than leaving ambiguous state, and error messages point to the specific recovery action needed.

### State corruption

| Scenario | Error | Recovery |
|----------|-------|----------|
| Missing state table | "Cannot backup invalid state schema" on `state migrate` | `sqb state reset --auto-approve` then `sqb state init` |
| Missing state column | Same | Same |
| Wrong state column type | Same | Same |
| Deleted backup schema (explicit id) | Rollback blocks with backup-id error | Use a different backup or reset |
| All backups deleted | "No state backup is available for rollback" | `sqb state reset --auto-approve` then reinitialize |

State corruption is detected by schema validation during `state migrate`. If the current state schema is invalid, SQLBuild refuses to back it up (to avoid persisting a broken snapshot) and directs you to reset.

### Warehouse drift

| Scenario | Detection | Recovery |
|----------|-----------|----------|
| Missing logical VDE view | `sqb reconcile` reports missing view | `sqb reconcile repair-view` for the affected model |
| Missing physical relation | `sqb reconcile` reports it, `repair-view` blocks | Rebuild with `sqb build --select` |
| Logical target is a table, not a view | `repair-view` and `attach` block | Drop the table manually, then `repair-view` |
| Checkpoint physical relation missing | `sqb rollback` blocks | Use a more recent checkpoint, or rebuild |
| Promoted physical relation missing | `sqb promote` blocks | Rebuild the source VDE first |

### Lock conflicts

| Scenario | Error | Recovery |
|----------|-------|----------|
| VDE locked by another process | "virtual environment is locked" | Wait for the other process, or clear the lock |
| Lock held by crashed process | Same | `sqb state locks clear` with `--force` |

Only clear locks when you are certain the holding operation is no longer running.

### Interrupted operations

| Scenario | Behavior | Recovery |
|----------|----------|----------|
| Interrupted adopt | Failed operation recorded. Physical schema may have partial artifacts. | `sqb reconcile` to diagnose, manual repair if needed, retry. |
| Interrupted detach | Failed operation recorded. VDE stays finalized. Physical version preserved. | `sqb reconcile` to diagnose, retry detach. |
| Interrupted promotion | Failed operation recorded. Target VDE lock released. | Retry promote. |

There is no automatic resume command for interrupted operations. SQLBuild records the failure in `state_operations` and `state_operation_events`, preserves VDE refs and checkpoints, and leaves recovery to the operator.

To inspect a failed operation:

```sql
SELECT operation_id, operation_type, status, virtual_environment_name
FROM sqlbuild_state.state_operations
WHERE status = 'failed';

SELECT operation_id, action, status, message
FROM sqlbuild_state.state_operation_events
WHERE operation_id = '<id>'
ORDER BY created_at;
```

### Mode guards

SQLBuild blocks operations that don't apply to the current mode:

| Operation | Direct mode | Virtual mode |
|-----------|-------------|--------------|
| `sqb state` subcommands | Blocked | Allowed |
| `sqb build --no-tests --no-audits` | Allowed | Blocked (use `sqb build`) |
| `sqb build --defer-to` | Allowed | Blocked (VDE refs handle upstream resolution) |
| `sqb promote` | Blocked | Allowed |
| `sqb rollback` | Blocked | Allowed |
| `sqb reconcile` | Blocked | Allowed |

### Detached VDE guards

After `sqb state detach`, the VDE is marked `detached` and blocked from further virtual operations:

| Operation | Behavior |
|-----------|----------|
| `sqb build` | Blocks: "virtual environment is detached" |
| `sqb promote --from <detached>` | Blocks |
| `sqb promote --to <detached>` | Blocks |
| `sqb rollback` | Blocks |

The project can continue in direct mode or re-adopt to return to virtual mode.

### Adopt guards

| Condition | Error |
|-----------|-------|
| No `unsuffixed_virtual_env` configured | Blocks with config guidance |
| Copy fallback needed without `--allow-copy` | `requires --allow-copy` |
| Wrong typed confirmation | Cancelled, no changes made |

### Detach guards

| Condition | Error |
|-----------|-------|
| VDE not finalized | "requires a finalized virtual environment" |
| Copy fallback needed without `--allow-copy` | `requires --allow-copy` |
| Wrong typed confirmation | Cancelled, no changes made |

### General recovery strategy

1. **Diagnose** with `sqb reconcile` or by querying state tables directly
2. **Repair views** with `sqb reconcile repair-view` for missing/broken logical views
3. **Rebuild** with `sqb build --select <model>` for missing physical versions
4. **Roll back** with `sqb rollback` to restore a prior finalized state
5. **Reset state** with `sqb state reset --auto-approve` as a last resort (drops all virtual state)

When in doubt, `sqb reconcile` is the starting point. It reports what's wrong without changing anything.

## Overview

Source: `integrations/dagster.mdx`

Orchestrate SQLBuild pipelines with Dagster scheduling, retries, and asset UI.

SQLBuild includes a Dagster integration that maps your project's models, sources, seeds, functions, loaders, tasks, assets, tests, audits, scenarios, and Python checks into Dagster assets and asset checks. SQLBuild handles the SQL transformation layer. Dagster handles scheduling, retries, alerting, and the asset-centric UI.

### Install

```bash
uv pip install 'sqlbuild[dagster]'
# or
pip install 'sqlbuild[dagster]'
```

This installs `dagster` and `dagster-webserver` alongside SQLBuild.

### Try it

```bash
sqb playground --template dagster
cd sqlbuild-playground
dagster dev -f dagster/definitions.py
```

This creates the waffle shop project with a `dagster/definitions.py` that includes asset definitions, scenario checks, and a configured resource. Open the Dagster UI, materialize the assets, then run the scenario checks.

### How it works

1. `sqb compile --dag` generates a static `sqlbuild_dag.json` artifact with your project's full graph (nodes, edges, checks)
2. `@sqlbuild_assets()` reads the artifact and creates one Dagster `AssetSpec` per source, seed, model, function, loader, task, and asset, with dependency edges preserved
3. `SqlBuildCliResource` shells out to `sqb build`, `sqb test`, `sqb scenario test`, etc. as subprocesses
4. Execution results (materializations, audit pass/fail, scenario outcomes) are parsed from structured JSON and emitted as Dagster `MaterializeResult` and `AssetCheckResult` events

SQLBuild tests, audits, and Python checks become Dagster asset checks. Scenarios become asset checks attached to the models they exercise.

### Quickstart

```python
# definitions.py
from sqlbuild.integrations.dagster import (
    SqlBuildCliResource,
    SqlBuildProject,
    sqlbuild_assets,
)
import dagster as dg

project = SqlBuildProject(project_dir=".")
project.prepare_if_dev()  # auto-generates DAG artifact in dagster dev

@sqlbuild_assets(project=project)
def my_sqlbuild_assets(context: dg.AssetExecutionContext, sqb: SqlBuildCliResource):
    yield from sqb.cli(["build"], context=context).stream()

defs = dg.Definitions(
    assets=[my_sqlbuild_assets],
    resources={"sqb": SqlBuildCliResource(project)},
)
```

```bash
dagster dev -f definitions.py
```

Dagster discovers every SQLBuild model, loader, task, and asset as a Dagster asset. Selecting a subset in the Dagster UI automatically scopes the `sqb build` invocation to those nodes via `--select`.

For production deployments, use `project.prepare()` or `sqb compile --dag` to generate the DAG artifact explicitly in your CI pipeline.

### Asset selection

When you select a subset of assets in the Dagster UI, the integration automatically:

1. Maps selected Dagster asset keys back to SQLBuild node names using the DAG artifact
2. Writes the selectors to a temporary file
3. Passes `--select-file` to the `sqb` CLI so only the selected models are built

This means Dagster's asset subsetting works naturally with SQLBuild's selector system.

### Checks

SQLBuild tests, audits, scenarios, and Python checks are registered as Dagster asset checks:

- **Unit tests** become checks attached to the models they test
- **Audits** become checks attached to the model or source they audit, with severity mapped to `AssetCheckSeverity.ERROR` or `AssetCheckSeverity.WARN`
- **Scenarios** become checks attached to the models they exercise
- **Python checks** (`@check`) become checks attached to the tasks, assets, or loaders they validate

Check results are emitted with pass/fail status and metadata from the execution JSON.

### Scenarios as checks

Scenarios can be included as asset checks alongside tests and audits (the default), or run separately:

```python
from sqlbuild.integrations.dagster import sqlbuild_assets, sqlbuild_scenario_checks

# Include scenario checks with other assets (default)
@sqlbuild_assets(project=project, include_scenario_checks=True)
def my_assets(context, sqb):
    yield from sqb.cli(["build"], context=context).stream()

# Or run scenarios separately
@sqlbuild_scenario_checks(project=project)
def my_scenario_checks(context, sqb):
    yield from sqb.cli(["scenario", "test"], context=context).stream()
```

### Project preparation

`SqlBuildProject.prepare()` regenerates the DAG artifact by running `sqb compile --dag`. Use `prepare_if_dev()` to only regenerate during local development:

```python
project = SqlBuildProject(project_dir=".")
project.prepare_if_dev()  # only runs when DAGSTER_IS_DEV_CLI is set
```

This keeps the Dagster UI in sync with your latest model changes during development without regenerating in production.

### Translator

Customise how SQLBuild nodes map to Dagster assets by subclassing `SqlBuildDagsterTranslator`:

```python
from sqlbuild.integrations.dagster import SqlBuildDagsterTranslator
import dagster as dg

class MyTranslator(SqlBuildDagsterTranslator):
    def get_asset_key(self, node):
        # Prefix all asset keys with the project name
        return dg.AssetKey(["my_project", *node["asset_key"]])

    def get_group_name(self, node):
        # Group by materialization type instead of kind
        return node.get("materialization_type", "other")

@sqlbuild_assets(project=project, translator=MyTranslator())
def my_assets(context, sqb):
    yield from sqb.cli(["build"], context=context).stream()
```

See the [API reference](/integrations/dagster-reference) for all translator methods.

## API Reference

Source: `integrations/dagster-reference.mdx`

Dagster integration classes, decorators, and translator hooks.

### SqlBuildProject

Project metadata and DAG artifact preparation.

```python
from sqlbuild.integrations.dagster import SqlBuildProject

project = SqlBuildProject(
    project_dir=".",
    target_path="target",
    dag_filename="sqlbuild_dag.json",
    sqb_command=("sqb",),
    prepare_project_cli_args=("compile", "--dag"),
)
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `project_dir` | (required) | Path to the SQLBuild project root |
| `target_path` | `"target"` | Relative path to the target directory |
| `dag_filename` | `"sqlbuild_dag.json"` | DAG artifact filename |
| `sqb_command` | `("sqb",)` | Command to invoke SQLBuild CLI |
| `prepare_project_cli_args` | `("compile", "--dag")` | CLI args used by `prepare()` to generate the DAG |

#### Methods

| Method | Description |
|--------|-------------|
| `dag_path` | Property. Returns the full path to the DAG artifact (`project_dir / target_path / dag_filename`). |
| `prepare()` | Runs `sqb compile --dag <dag_path>` to generate the DAG artifact. Raises `DagsterProjectPrepareError` on failure. |
| `prepare_if_dev()` | Calls `prepare()` only when the `DAGSTER_IS_DEV_CLI` environment variable is set. |

### SqlBuildCliResource

Dagster `ConfigurableResource` that shells out to the SQLBuild CLI.

```python
from sqlbuild.integrations.dagster import SqlBuildCliResource, SqlBuildProject

# From a project
resource = SqlBuildCliResource(SqlBuildProject(project_dir="."))

# Or with explicit paths
resource = SqlBuildCliResource(
    project_dir=".",
    sqb_command=["sqb"],
    dag_path="target/sqlbuild_dag.json",
)
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `project_dir` | `"."` | Path to the SQLBuild project root, or a `SqlBuildProject` instance |
| `sqb_command` | `["sqb"]` | Command to invoke SQLBuild CLI |
| `dag_path` | `None` | Path to the DAG artifact. When set, enables asset selection bridging and structured event emission. |

#### cli()

Create a CLI invocation for the provided command arguments.

```python
invocation = resource.cli(
    ["build"],
    context=context,        # Dagster execution context (optional)
    raise_on_error=True,    # raise Failure on non-zero exit (default)
)
```

Returns a `SqlBuildCliInvocation`.

### SqlBuildCliInvocation

A running or completed SQLBuild CLI subprocess.

#### Methods

| Method | Description |
|--------|-------------|
| `wait()` | Wait for the process to complete. Streams stdout/stderr in real time. Returns `self`. |
| `stream()` | Wait for the process, then yield Dagster `MaterializeResult` and `AssetCheckResult` events parsed from execution JSON. |
| `is_successful()` | Returns `True` if exit code is 0. |
| `get_error()` | Returns a Dagster `Failure` if the process failed, `None` otherwise. |
| `get_artifact(name)` | Read a JSON artifact from the project's `target/` directory. |

#### Properties

| Property | Description |
|----------|-------------|
| `stdout` | Captured stdout after `wait()` or `stream()`. |
| `stderr` | Captured stderr after `wait()` or `stream()`. |
| `returncode` | Process exit code after completion. |
| `execution_payload` | Parsed execution JSON, if available. |

#### stream() behavior

`stream()` is the primary way to emit Dagster events from a SQLBuild execution:

1. Waits for the subprocess to complete while streaming output to stdout/stderr
2. Reads the structured execution JSON (from `--json-output` tempfile)
3. Maps each completed asset to a `MaterializeResult` with metadata (status, duration, row counts)
4. Maps each check result to an `AssetCheckResult` with pass/fail, severity, and check metadata
5. If the DAG artifact is available, results are matched to the correct Dagster asset keys
6. Raises `Failure` if the process exited non-zero and `raise_on_error` is set

### sqlbuild_assets

Decorator that creates a Dagster multi-asset definition from a SQLBuild DAG artifact.

```python
from sqlbuild.integrations.dagster import sqlbuild_assets

@sqlbuild_assets(
    project=project,                    # or dag=path_or_dict
    translator=MyTranslator(),          # optional
    name="my_sqlbuild_assets",          # optional
    include_scenario_checks=True,       # default: True
    required_resource_keys={"sqb"},     # optional
)
def my_assets(context, sqb):
    yield from sqb.cli(["build"], context=context).stream()
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `project` | `None` | `SqlBuildProject` instance. Mutually exclusive with `dag`. |
| `dag` | `None` | DAG artifact as a path, string, or pre-loaded dict. Mutually exclusive with `project`. |
| `translator` | `SqlBuildDagsterTranslator()` | Translator for asset keys, groups, tags, and metadata. |
| `name` | `None` | Override the Dagster multi-asset name. |
| `include_scenario_checks` | `True` | Whether to include scenario checks alongside test and audit checks. |
| `required_resource_keys` | `None` | Additional Dagster resource keys to require. |

If neither `project` nor `dag` is provided, the decorator looks for `target/sqlbuild_dag.json` in the current directory.

### sqlbuild_scenario_checks

Decorator that creates a Dagster multi-asset-check definition for SQLBuild scenarios only. Useful when you want to run scenarios separately from the main build.

```python
from sqlbuild.integrations.dagster import sqlbuild_scenario_checks

@sqlbuild_scenario_checks(project=project)
def my_scenario_checks(context, sqb):
    yield from sqb.cli(["scenario", "test"], context=context).stream()
```

Parameters are the same as `sqlbuild_assets` except there is no `include_scenario_checks` flag.

### SqlBuildDagsterTranslator

Customise how SQLBuild DAG nodes map to Dagster asset metadata. Subclass and override any method.

#### Methods

| Method | Arguments | Returns | Default behavior |
|--------|-----------|---------|------------------|
| `get_asset_key` | `node` | `AssetKey` | `AssetKey(node["asset_key"])` |
| `get_group_name` | `node` | `str \| None` | Node kind (e.g. `"model"`, `"source"`) |
| `get_tags` | `node` | `dict[str, str]` | `sqlbuild/kind` tag plus any model tags |
| `get_metadata` | `node` | `dict[str, Any]` | `sqlbuild_id`, `sqlbuild_name`, `sqlbuild_kind`, path, target, description, columns |
| `get_description` | `node` | `str \| None` | Node description if present |
| `get_check_name` | `check` | `str` | `"{kind}__{name}"` with optional column/target suffix |
| `get_check_metadata` | `check` | `dict[str, Any]` | Check ID, kind, name, and selector |

#### Node structure

Each `node` dict passed to translator methods contains:

```json
{
  "id": "model:fact_orders",
  "kind": "model",
  "name": "fact_orders",
  "asset_key": ["dev", "fact_orders"],
  "target": {
    "database": null,
    "schema": "dev",
    "name": "fact_orders",
    "qualified_name": "dev.fact_orders"
  },
  "path": "models/marts/fact_orders.sql",
  "description": "Order fact table with waffle and payment details.",
  "tags": ["marts"],
  "columns": [
    {"name": "order_id", "type": "INTEGER"}
  ],
  "materialization_type": "table"
}
```

Python node asset keys use a two-part key with the node kind as prefix:

| Kind | Asset key example |
|------|-------------------|
| Task | `("task", "prepare_orders")` |
| Asset | `("asset", "orders_export")` |
| Loader | `("loader", "raw_orders")` |

#### Check structure

Each `check` dict passed to check translator methods contains:

```json
{
  "id": "audit:not_null:model:fact_orders:order_id",
  "kind": "audit",
  "name": "not_null",
  "checked_asset_ids": ["model:fact_orders"],
  "path": "audits/generic/not_null.sql",
  "severity": "error",
  "attached_target_name": "fact_orders",
  "attached_column_name": "order_id"
}
```

Scenario checks include additional fields:

```json
{
  "id": "scenario:daily_revenue_minimal",
  "kind": "scenario",
  "name": "daily_revenue_minimal",
  "checked_asset_ids": ["model:daily_revenue"],
  "path": "tests/scenarios/revenue/daily_revenue_minimal.sql",
  "assertion_names": ["no_negative_revenue"],
  "expected_model_names": ["daily_revenue"],
  "fixture_refs": ["stg_orders", "stg_payments"]
}
```

## Rivers

Source: `integrations/rivers.mdx`

Orchestrate SQLBuild pipelines with Rivers scheduling, jobs, and asset tracking.

SQLBuild includes a Rivers integration that maps your project's models, sources, seeds, loaders, tasks, assets, and functions into Rivers assets with dependency edges preserved. SQLBuild handles the SQL transformation layer. Rivers handles scheduling, execution, and the asset-centric UI.

### Install

```bash
pip install 'sqlbuild[rivers]'
# or
uv pip install 'sqlbuild[rivers]'
```

This installs `rivers` alongside SQLBuild.

### Try it

```bash
sqb playground --template rivers
cd sqlbuild-playground
uv run rivers dev rivers_pipeline.definitions
```

This creates the waffle shop project with a `rivers_pipeline/definitions.py` that includes asset definitions and a configured job. Open the Rivers UI to inspect assets and trigger materializations.

### How it works

1. `sqb compile --dag` generates a static `sqlbuild_dag.json` artifact with your project's full graph (nodes, edges)
2. `@sqlbuild_assets()` reads the artifact and creates one Rivers `AssetDef` per source, loader, seed, model, function, task, and asset, with dependency edges preserved
3. The decorated function runs `sqb build` as a subprocess and yields `Materialization` events for each output

### Quickstart

```python
# definitions.py
from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import rivers as rs

from sqlbuild.integrations.rivers import SqlBuildProject, sqlbuild_assets

PROJECT_DIR = Path(__file__).resolve().parent.parent
SQLBUILD_PROJECT = SqlBuildProject(project_dir=PROJECT_DIR)
SQLBUILD_PROJECT.prepare_if_dev()

@sqlbuild_assets(project=SQLBUILD_PROJECT)
def my_assets(context: Any) -> Iterator[Any]:
    completed = subprocess.run(
        ["sqb", "build"],
        cwd=PROJECT_DIR,
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr or completed.stdout)
    for output_name in context.output_selection:
        yield rs.Materialization(output_name=output_name)

repo = rs.CodeRepository(
    assets=[my_assets],
    jobs=[
        rs.Job(
            name="sqlbuild_pipeline",
            assets=[my_assets],
            executor=rs.Executor.in_process(),
        ),
    ],
)
```

### SqlBuildProject

`SqlBuildProject` manages paths and DAG artifact generation:

```python
project = SqlBuildProject(project_dir=Path("."))
```

| Field | Default | Description |
|-------|---------|-------------|
| `project_dir` | required | Path to the SQLBuild project root |
| `target_path` | `target` | Directory for build artifacts |
| `dag_filename` | `sqlbuild_dag.json` | DAG artifact filename |
| `sqb_command` | `("sqb",)` | Command to invoke SQLBuild |
| `prepare_project_cli_args` | `("compile", "--dag")` | CLI arguments for DAG generation |

#### Methods

| Method | Description |
|--------|-------------|
| `prepare()` | Generate the DAG artifact by running `sqb compile --dag` |
| `prepare_if_dev()` | Generate the DAG artifact only when `RIVERS_DEPLOYMENT=dev` |
| `dag_path` | Property returning the full path to the DAG artifact |

Use `prepare_if_dev()` so the DAG artifact is auto-generated during local development but not during production deployments where it should already exist.

### sqlbuild_assets

The `@sqlbuild_assets()` decorator creates a Rivers multi-asset definition from a SQLBuild DAG artifact:

```python
@sqlbuild_assets(project=project)
def my_assets(context):
    ...
```

| Parameter | Description |
|-----------|-------------|
| `project` | `SqlBuildProject` instance (generates and locates the DAG artifact) |
| `dag` | Alternative: pass a DAG path or dict directly instead of a project |
| `translator` | Optional `SqlBuildRiversTranslator` for custom name/tag/metadata mapping |
| `name` | Optional asset name override |

Pass either `project` or `dag`, not both.

### SqlBuildRiversTranslator

Override the default mapping from SQLBuild DAG nodes to Rivers asset metadata:

```python
from sqlbuild.integrations.rivers import SqlBuildRiversTranslator

class CustomTranslator(SqlBuildRiversTranslator):
    def get_group_name(self, node):
        return "my_custom_group"

    def get_tags(self, node):
        tags = super().get_tags(node)
        tags.append("team:analytics")
        return tags

@sqlbuild_assets(project=project, translator=CustomTranslator())
def my_assets(context):
    ...
```

#### Translator methods

| Method | Default behavior |
|--------|-----------------|
| `get_asset_name(node)` | Joins the asset key parts with `__` (e.g. `task__prepare_orders`, `asset__orders_export`) |
| `get_group_name(node)` | Uses the project name |
| `get_tags(node)` | Includes `sqlbuild/kind:<kind>` plus model tags |
| `get_kinds(node)` | Returns `["sqlbuild", "<materialization_type>"]` |
| `get_metadata(node)` | Includes SQLBuild name, kind, path, target, columns, etc. |

### Running locally

Run the pipeline directly without the Rivers UI:

```bash
uv run python rivers_pipeline/definitions.py
```

Or start the Rivers development server:

```bash
uv run rivers dev rivers_pipeline.definitions
```

## dlt

Source: `integrations/dlt.mdx`

Declarative dlt sources in YAML, or full dlt pipelines inside Python source loaders.

[dlt](https://dlthub.com) is an open-source Python library for loading data from APIs, databases, cloud storage, and more. SQLBuild integrates with dlt two ways:

- **Declarative dlt sources** - configure dlt directly in your source YAML, no Python code. SQLBuild runs the dlt pipeline as part of the build lifecycle. Best for the common REST API, SQL database, and filesystem cases.
- **dlt inside a Python loader** - wrap any `dlt.pipeline(...)` in a SQLBuild [source loader](/concepts/python-nodes/loaders) for full control when you need dlt features beyond the declarative surface.

### Install

```bash
pip install 'sqlbuild[dlt]'
# or
uv pip install 'sqlbuild[dlt]'
```

This installs dlt with the `duckdb`, `filesystem`, and `sql_database` extras alongside SQLBuild.

### Declarative dlt sources (YAML)

Declare a `dlt_sources` list in a `sources/*.yml` file. Each entry has a `type`, a `config` block passed to the dlt source, and a list of `resources` that become SQLBuild managed sources. SQLBuild generates a synthetic loader per resource and writes into the database its adapter manages, no Python and no destination setup required.

Supported source types: `rest_api`, `sql_database`, `filesystem`.

#### REST API

```yaml
# sources/github.yml
dlt_sources:
  - type: rest_api
    config:
      client:
        base_url: https://api.github.com/
        headers:
          Authorization: "Bearer ${github_token}"
        paginator:
          type: header_link
    resources:
      - name: raw_github_issues
        write_disposition: append
        endpoint:
          path: "repos/${github_owner}/${github_repo}/issues"
          params:
            state: all
            per_page: 100
```

`rest_api` requires `client.base_url` in `config`. Each resource needs an `endpoint` mapping; the dlt resource name comes from `endpoint.name` if present, otherwise the resource `name`.

#### SQL database

```yaml
# sources/postgres.yml
dlt_sources:
  - type: sql_database
    config:
      credentials: "${postgres_connection_string}"
    resources:
      - name: raw_customers
        table: customers
        write_disposition: merge
        primary_key: id
```

`sql_database` requires `credentials` in `config`, and each resource requires a `table`.

#### Filesystem

```yaml
# sources/files.yml
dlt_sources:
  - type: filesystem
    config:
      bucket_url: "s3://my-bucket/events/"
    resources:
      - name: raw_events
        write_disposition: append
```

`filesystem` requires `bucket_url` in `config`.

#### Resource options

| Key | Description |
|-----|-------------|
| `name` | Source name SQLBuild exposes (referenced via `__source("name")`). Required. |
| `table` | Source table to replicate (`sql_database` only). Required for that type. |
| `endpoint` | Endpoint mapping (`rest_api` only). Required for that type. |
| `write_disposition` | dlt write disposition: `replace`, `append`, or `merge`. `merge` requires `primary_key`. |
| `primary_key` / `merge_key` | dlt keys for `merge`. |
| `incremental` | dlt incremental config mapping (e.g. cursor column and start value). |
| `schema` | Per-resource schema override (falls back to the group `schema`). |

Use SQLBuild's `write_disposition` (dlt's term), not `write_strategy`. `delete_insert` is not available declaratively; use a Python loader for that. Config values support SQLBuild's [interpolation](/concepts/interpolation): `${name}` for a project variable, `${ENV:NAME}` for an environment variable, and `${CTX:...}` for context, resolved at load time, so credentials stay out of the YAML.

#### Destination

By default each resource loads into the database SQLBuild's adapter manages, with the dataset/schema derived from your target. An optional `destination` mapping passes extra settings to the dlt destination, but it cannot set `credentials`, `dataset_name`, or `default_schema_name` (SQLBuild manages those):

```yaml
dlt_sources:
  - type: rest_api
    destination:
      loader_file_format: parquet
    config:
      client:
        base_url: https://api.example.com/
    resources:
      - name: raw_widgets
        endpoint:
          path: widgets
```

#### Reference in models

Declared resources are managed sources, reference them like any other source:

```sql
SELECT id, title, state FROM __source("raw_github_issues")
```

### dlt inside a Python loader

When you need dlt capabilities beyond the declarative surface (custom transforms, `delete_insert`, sources not covered above), wrap a dlt pipeline in a [source loader](/concepts/python-nodes/loaders). The loader calls `dlt.pipeline(...).run(...)` and returns `None`; dlt handles the writes and SQLBuild treats the source as loaded.

```python
# loaders/github_sources.py
import dlt
from dlt.sources.rest_api import rest_api_source
from sqlbuild.loaders import loader
from sqlbuild.executor.load.models import LoaderContext

@loader
def raw_github_issues(ctx: LoaderContext):
    source = rest_api_source({
        "client": {
            "base_url": "https://api.github.com/",
            "headers": {"Authorization": f"Bearer {ctx.vars['github_token']}"},
            "paginator": {"type": "header_link"},
        },
        "resources": [{
            "name": "issues",
            "endpoint": {
                "path": "repos/{owner}/{repo}/issues",
                "params": {
                    "owner": ctx.vars["github_owner"],
                    "repo": ctx.vars["github_repo"],
                    "state": "all",
                    "per_page": 100,
                },
            },
        }],
    })

    pipeline = dlt.pipeline(
        pipeline_name="github_issues",
        destination=dlt.destinations.duckdb(ctx.connection),
        dataset_name=ctx.destination_schema or "main",
    )
    pipeline.run(source)
```

Bind it to a source with `managed: true` in `sources/*.yml`:

```yaml
# sources/github.yml
sources:
  - name: raw_github_issues
    managed: true
    table: issues
    columns:
      - name: id
        type: INTEGER
      - name: title
        type: VARCHAR
```

#### DuckDB connection sharing

With the DuckDB adapter, pass `ctx.connection` to dlt's DuckDB destination to reuse SQLBuild's open connection, so dlt writes into the same database without a separate connection string:

```python
pipeline = dlt.pipeline(
    pipeline_name="my_pipeline",
    destination=dlt.destinations.duckdb(ctx.connection),
    dataset_name=ctx.destination_schema or "main",
)
```

#### Warehouse destinations

For Snowflake, BigQuery, or Databricks, configure dlt with its own credentials. dlt writes directly to the warehouse, and SQLBuild reads the resulting tables as sources:

```python
pipeline = dlt.pipeline(
    pipeline_name="api_data",
    destination="snowflake",
    dataset_name=ctx.destination_schema or "public",
)
```

Configure dlt credentials via its own `secrets.toml` or environment variables, as in the [dlt documentation](https://dlthub.com/docs/general-usage/credentials/setup).

### Build integration

Whether declarative or Python, loaders run automatically during `sqb build` (when `auto_load_sources` is enabled), so dlt pipelines execute as part of the normal build lifecycle:

```bash
sqb build            # loaders run, then models build
sqb build --no-load  # skip loading, use existing source data
sqb load             # run loaders standalone
```

See [Loaders](/concepts/python-nodes/loaders) for write strategies, the loader context API, auto-load behavior, and source deferral.

## ingestr

Source: `integrations/ingestr.mdx`

Declarative data ingestion from 50+ sources using ingestr.

[ingestr](https://github.com/bruin-data/ingestr) is an open-source CLI tool by [Bruin](https://github.com/bruin-data) that copies data from any source to any destination using a single command. SQLBuild integrates with ingestr as a declarative source loader - you configure the ingestion directly in your source YAML, and SQLBuild handles execution as part of the build lifecycle.

### Install

```bash
pip install 'sqlbuild[ingestr]'
# or
uv pip install 'sqlbuild[ingestr]'
```

This installs `ingestr` alongside SQLBuild. The `ingestr` CLI must be available on `PATH`.

### How it works

1. Declare an `ingestr` block on a source in `sources/*.yml`
2. SQLBuild generates a synthetic loader that calls `ingestr ingest` as a subprocess
3. ingestr reads from the configured source and writes directly to the SQLBuild adapter's database
4. The destination URI is built automatically from your SQLBuild connection config - no manual destination setup

No Python loader code is needed. The YAML declaration is the entire configuration.

### Example: PostgreSQL to DuckDB

Replicate a table from PostgreSQL into your local DuckDB project:

```yaml
# sources/raw.yml
sources:
  - name: raw_orders
    table: orders
    ingestr:
      source_uri: "postgresql://user:pass@host:5432/mydb"
      source_table: "public.orders"
```

That's it. Run `sqb load` or `sqb build` and ingestr copies the `orders` table into your project.

### Example: Stripe with incremental merge

Load Stripe charges with incremental merge on a primary key:

```yaml
sources:
  - name: raw_stripe_charges
    table: charges
    ingestr:
      source_uri: "stripe://${stripe_api_key}"
      source_table: "charges"
      strategy: merge
      primary_key: id
      incremental_key: created
```

On subsequent runs, ingestr merges new and updated records based on the `id` column, using `created` to detect changes.

### Configuration reference

The `ingestr` block on a source supports the following fields:

| Field | Required | Description |
|-------|----------|-------------|
| `source_uri` | Yes | ingestr source connection URI (e.g. `postgresql://...`, `stripe://...`, `shopify://...`) |
| `source_table` | Yes | Source table or resource name to ingest |
| `strategy` | No | Ingestion strategy: `replace`, `append`, `merge`, `delete+insert`, or `truncate+insert` |
| `incremental_key` | No | Column used for incremental change detection |
| `primary_key` | No | Primary key column(s) for merge strategy (string or list) |
| `columns` | No | Comma-separated column list to select from the source |
| `extra_args` | No | Additional CLI arguments passed to `ingestr ingest` (list of strings) |

#### Strategy mapping

| Strategy | Behavior |
|----------|----------|
| `replace` | Drop and recreate the destination table (default when no strategy is set) |
| `append` | Insert all rows without deduplication |
| `merge` | Upsert based on `primary_key`, using `incremental_key` for change detection |
| `delete+insert` | Delete matching rows by `incremental_key` range, then insert replacements |
| `truncate+insert` | Truncate destination table, then insert all rows |

### Template variables

All string fields in the `ingestr` block support SQLBuild project variable substitution and context templates:

```yaml
sources:
  - name: raw_orders
    ingestr:
      source_uri: "postgresql://${pg_user}:${pg_password}@${pg_host}:5432/${pg_database}"
      source_table: "public.orders"
```

Variables are resolved from the project's merged variable config (project + target + local).

Set sensitive values in `sqlbuild_local.toml` (gitignored):

```toml
[vars]
pg_user = "readonly"
pg_password = "secret"
pg_host = "prod-db.example.com"
pg_database = "analytics"
stripe_api_key = "sk_live_..."
```

### Destination URI

SQLBuild automatically builds the ingestr destination URI from your adapter connection config. All supported adapters work without manual destination configuration:

| Adapter | Destination URI format |
|---------|----------------------|
| DuckDB | `duckdb:///path/to/db.duckdb` |
| MotherDuck | `motherduck://database` |
| PostgreSQL | `postgresql://user:pass@host:port/db` |
| Snowflake | `snowflake://user:pass@account/db/schema` |
| BigQuery | `bigquery://project` |
| Databricks | `databricks://token:...@host` |
| SQL Server | `mssql://user:pass@host:port/db` |

### Reload

When `--reload` is passed, ingestr runs with `--full-refresh`, forcing a complete reload regardless of the configured strategy:

```bash
sqb load --reload
sqb build --reload
```

### Build integration

ingestr sources are managed sources - they participate in the same lifecycle as Python loaders:

```bash
# ingestr runs automatically before dependent models
sqb build

# run ingestr sources standalone
sqb load

# skip loading
sqb build --no-load
```

See [Loaders](/concepts/python-nodes/loaders) for details on auto-load behavior, source deferral, and the `--load` / `--no-load` / `--reload` flags.

### Supported sources

ingestr supports 50+ sources including databases, SaaS APIs, and file systems. See the [ingestr documentation](https://bruin-data.github.io/ingestr/) for the full list of supported sources and their URI formats.

## init

Source: `cli/init.mdx`

Scaffold a new SQLBuild project.

## sqb init

Creates a new SQLBuild project with a minimal directory structure and configuration files.

### Usage

```bash
sqb init
```

No flags. Run in the directory where you want to create the project.

### Project layout

`sqb init` creates the configuration, linter settings, and empty resource directories needed for a standalone project:

```text
my-project/
  sqlbuild_project.toml
  .sqruff
  models/
    staging/
    marts/
  schemas/
  sources/
  seeds/
  loaders/
  tasks/
  assets/
  checks/
  hooks/
    sql/
    python/
  tests/
    unit/
    scenarios/
  functions/
    sql/
    python/
  macros/
  audits/
    generic/
    singular/
```

Empty directories contain `.gitkeep` files so the scaffold can be committed. Reusable attached
audit definitions belong in `audits/generic/`; standalone audits belong in `audits/singular/`.
Add reusable SQL lifecycle hooks to `hooks/sql/` and decorated Python lifecycle hooks to
`hooks/python/`; see [Hooks](/concepts/models/hooks).

The generated project uses DuckDB, creates a named `local` connection shared by `dev` and
`prod`, and defaults models to table materialization. Its configuration follows this shape:

```toml
adapter = "duckdb"
default_target = "dev"

[connections.local]
database = "my_project.duckdb"

[targets.dev]
connection = "local"
schema = "dev"

[targets.prod]
connection = "local"
schema = "prod"
```

The project name is derived from the current directory name, with hyphens converted to
underscores.

## playground

Source: `cli/playground.mdx`

Create a self-contained SQLBuild project to explore locally.

## sqb playground

Creates a self-contained waffle shop project with DuckDB. No warehouse credentials, no git clone, no external data - just a working project you can compile, build, test, and explore immediately.

### Usage

```bash
sqb playground [name]
```

The positional argument is the directory to create (default `sqlbuild-playground`). The template is chosen with `--template` (default `waffle_shop`).

### Templates

| Template | Description |
|----------|-------------|
| `waffle_shop` | Default. DuckDB-backed project with models, tests, scenarios, and macros. |
| `dagster` | Waffle shop project plus a `dagster/` directory with a ready-to-run `definitions.py`. |
| `rivers` | Waffle shop project plus a `rivers_pipeline/` directory with a Rivers repository definition. |
| `virtual` | Waffle shop with virtual environments enabled, a local DuckDB state store, loaders, and the full virtual lifecycle (build, promote, rollback). |
| `python_nodes` | A small DuckDB project demonstrating [Python nodes](/concepts/python-nodes/overview): a task feeding a loader, a model read by a Python asset through `ctx.relation(model(...))`, a soft-skip fan-in, `materialized=False`, and a Python check. |

### What it creates

A complete DuckDB-backed project with:

- Staging views, fact/dimension tables, and incremental models
- Sources with inline expression data (no external setup)
- Seeds, SQL functions, and a custom materialization
- Built-in and custom audits
- SQL unit tests and multi-model tests
- E2E scenario tests
- Python macros
- AI agent skill files (auto-installed for OpenCode, Claude Code, and other agents)

The `dagster` template adds:

- `dagster/definitions.py` - Dagster definitions with `sqlbuild_assets`, `sqlbuild_scenario_checks`, and `SqlBuildCliResource`
- `dagster/README.md` - Setup instructions

The `python_nodes` template instead creates a focused Python-nodes project:

- `tasks/orders.py`, `loaders/orders.py`, `assets/orders_export.py`, `checks/orders_export.py`
- A `fact_orders` SQL model over a managed `raw_orders` source
- Examples of the SQL boundary, `ctx.relation(model(...))`, soft-skip fan-in, and a Python check

### Examples

```bash
# Default waffle shop
sqb playground waffle-shop
cd waffle-shop
sqb build

# With Dagster integration
sqb playground --template dagster
cd sqlbuild-playground
uv pip install 'sqlbuild[dagster]'
dagster dev -f dagster/definitions.py

# With Rivers integration
sqb playground --template rivers
cd sqlbuild-playground
uv pip install 'sqlbuild[rivers]'
uv run rivers dev rivers_pipeline.definitions

# With virtual environments
sqb playground --template virtual
cd sqlbuild-playground
sqb state init
sqb build
sqb build --virtual-env pr
sqb promote --from pr --to dev

# With Python nodes
sqb playground --template python_nodes
cd sqlbuild-playground
sqb build --select +fact_orders --select +orders_export
sqb check --select +check_orders_export
```

### Notes

- The target directory must not already exist
- DuckDB is included as a core dependency - no extra installation needed
- The local DuckDB database file is created on the first build
- The Dagster template uses `prepare_if_dev()` to auto-generate the DAG artifact when Dagster starts in dev mode

## skills

Source: `cli/skills.mdx`

Install SQLBuild skill files for AI coding agents.

## sqb skills

Install or update SQLBuild skill files so AI coding agents (Claude Code, OpenCode, Cursor, etc.) understand your project's framework, syntax, and conventions.

Write the packaged SQLBuild skill file to agent-specific locations in your project.

```bash
sqb skills [flags]
```

### Flags

| Flag | Description |
|------|-------------|
| `--target` | Specify agent targets to install for. Can be passed multiple times. |
| `--global` | Install to global agent config directories instead of project-local |
| `--force` | Overwrite existing skill files even if they were not generated by SQLBuild |

### Targets

Three agent targets are supported:

| Target | Local path | Global path |
|--------|-----------|-------------|
| `opencode` | `.opencode/skills/sqlbuild/SKILL.md` | `~/.config/opencode/skills/sqlbuild/SKILL.md` |
| `claude` | `.claude/skills/sqlbuild/SKILL.md` | `~/.claude/skills/sqlbuild/SKILL.md` |
| `agents` | `.agents/skills/sqlbuild/SKILL.md` | `~/.agents/skills/sqlbuild/SKILL.md` |

By default, SQLBuild installs `agents` and `claude`. OpenCode consumes the shared `.agents`
skill, while Claude requires its `.claude` copy. The `opencode` target remains available as an
explicit override for installations that require `.opencode`:

```bash
# Install the agents and claude targets (default)
sqb skills

# Install for Claude Code only
sqb skills --target claude

# Install for OpenCode and Claude
sqb skills --target opencode --target claude

# Install globally
sqb skills --global
```

### Overwrite behavior

Generated skill files include an ownership marker. `sqb skills` will:

- Overwrite files it previously generated (safe to rerun)
- Refuse to overwrite files that were manually created or edited (no marker)
- Overwrite any file when `--force` is passed

Normal project commands append a non-blocking notice when an installed, SQLBuild-owned generated
skill is stale. The command still runs normally.

### Configuration

Default targets can be set in `sqlbuild_project.toml` so the team shares the same agent config:

```toml
[skills]
targets = ["agents", "claude"]
auto_update = true
```

CLI `--target` flags override the TOML config.

Set `auto_update = true` to refresh stale generated skills during normal project commands. Auto
update reads the skill bundled with the installed SQLBuild package and rewrites only files marked
as SQLBuild-owned. It never overwrites a custom file or an unowned path collision.

### Playground

The playground command automatically runs `sqb skills` after creating the project, so AI agents are ready to use immediately:

```bash
sqb playground waffle-shop
cd waffle-shop
# Agent skill files are already installed
```

### Kata policy skills

`sqb skills` installs general SQLBuild framework guidance. `sqb kata skills` generates
project-specific guidance from the active Kata rules, options, thresholds, naming vocabulary, and
scoped deviations:

```bash
sqb kata skills
sqb kata skills --check
```

Use `--check` in CI to detect missing or stale policy guidance without rewriting files. Kata uses
the separate `sqlbuild-kata` skill path and refuses to overwrite divergent or unowned content. See
[Kata SQL Architecture Checks](/concepts/kata) and the [Kata CLI reference](/cli/kata).

## compile

Source: `cli/compile.mdx`

Compile models into resolved SQL, validate contracts, and write target artifacts - fully offline.

## sqb compile

Compiles all discovered models, seeds, audits, and tests. Resolves references, expands macros, validates SQL, checks column contracts, computes column lineage, and writes compiled artifacts to `target/`. The compile command is fully offline - it does not connect to the warehouse.

### Usage

```bash
sqb --project-dir <path> compile [flags]
```

### Flags

| Flag | Description |
|------|-------------|
| `--no-sql-validation` | Skip compile-time SQL syntax validation |
| `--defer-to` | Resolve unselected model references against another target |
| `--json` | Output the full compile report as JSON |
| `--manifest` | Generate `target/manifest.json` with project metadata |
| `--lineage-mode` | Column lineage mode: `fast` (default), `rich` (slower, more detail), or `none` |

### What compile does

1. **Discovery** - finds `sqlbuild_project.toml`, scans for models, sources, seeds, functions, audits, tests, and macros
2. **Graph resolution** - resolves `ref()` and `source()` calls, expands macros, orders models by dependency
3. **SQL validation** - validates SQL syntax (when SQL analysis is enabled)
4. **Column lineage** - analyzes column-level dependencies across models (fast mode by default)
5. **Contract validation** - checks declared column contracts against inferred query output
6. **Artifact write** - writes compiled SQL to `target/compiled/`

### Static analysis

When SQL analysis is enabled (default), compile performs static analysis on your models without connecting to the warehouse:

- **Column inference**: Infers output columns from each model's SQL, including through CTEs, subqueries, and JOINs
- **Column contract validation**: Under the default `settings.column_contract_mode = "implicit"`, a model with declared columns and no model-level `contract` declaration checks that every declared column exists in the statically inferred query output. `explicit` mode requires `contract enforced` to activate shape checks. Explicit type enforcement remains independent and verifies inferred types when possible
- **Column lineage**: Traces which source columns flow into each output column, including transform classification. See [Column Lineage](/concepts/column-lineage) for details

`sqb compile` checks SQL correctness, contracts, and lineage. [`sqb kata`](/cli/kata) compiles the
project and then applies its separately configured architecture policy. Kata is not run
automatically by `compile`.

#### Contract diagnostics

When a contract violation is found, compile reports it with source-annotated diagnostics:

```
error[K001]: declared column 'total_cents' was not found in statically inferred output for model 'fact_orders'
  model: fact_orders
  --> models/marts/fact_orders.sql:6:5
  6 |     total_cents (),
    |     ^^^^^^^^^^^
  = help: add total_cents to the SELECT list or correct/remove MODEL(columns (...)); MODEL(columns (...)) is validated using static SQL analysis because settings.column_contract_mode is "implicit" (the default). If this project intentionally uses columns only for metadata and audits, set [settings] column_contract_mode = "explicit"; models with contract enforced remain validated
```

The configuration guidance is an intentional project-policy choice, not a general error suppression. Fix the query or declaration when the model is intended to have a column contract. Diagnostics for `contract enforced` models do not recommend changing the project mode because explicit model contracts remain authoritative.

Diagnostic codes:

| Code | Meaning |
|------|---------|
| `K001` | A declared column is missing from the model's query output |
| `K002` | A column's inferred type does not match the declared type |
| `K003` | A column's type could not be proven (with `type_enforcement` enabled) |

Compile returns exit code `1` when any error-severity diagnostic is found, making it suitable for CI checks.

### Output

#### Text output (default)

```bash
sqb compile
```

```
Compile ready (12 models)

  stg_customers              OK  3 columns
  stg_orders                 OK  5 columns
  stg_payments               OK  4 columns
  fact_orders                OK  6 columns
  dim_customers              OK  4 columns
  daily_revenue              OK  3 columns
  ...

  Compiled: 12 models, 1 seed, 5 functions, 0 errors, 0 warnings
  Wrote: target/compiled/
```

Each model shows its name, status (OK or FAIL), and column count. Models with contract errors are marked FAIL.

#### JSON output

```bash
sqb compile --json
```

Returns a structured report including:

- `summary` - model, seed, function, audit, test, error, and warning counts
- `resources` - per-model details including column count, dependencies, lineage summary, and compiled SQL
- `diagnostics` - all contract violations with source locations
- `compile_timings` - timing breakdown for discovery, graph, lineage, contracts, and write phases
- `lineage_mode` - which lineage mode was used
- `artifacts` - paths to written files

### Column lineage modes

The `--lineage-mode` flag controls how column lineage is computed during compile:

| Mode | Description |
|------|-------------|
| `fast` | Default. Lightweight column extraction using SQL model metadata. |
| `rich` | Full SQL analysis with transform classification and deeper tracing. Slower on large projects. |
| `none` | Skip column lineage entirely. |

The JSON compile report includes a lineage summary for each model, not the full column graph. Use `sqb lineage <model>[.<column>]` to inspect lineage as a tree, edge list, or JSON. See [Column Lineage](/concepts/column-lineage) for details on analysis modes and transform types.

### Examples

```bash
# Basic compile
sqb compile

# Compile with full JSON report
sqb compile --json

# Compile with rich column lineage
sqb compile --lineage-mode rich

# Skip column lineage
sqb compile --lineage-mode none

# Generate manifest
sqb compile --manifest

# Skip SQL validation
sqb compile --no-sql-validation
```

## scope

Source: `cli/scope.mdx`

Inspect declaration visibility, usage, placement, and move impact offline.

`sqb scope` explains the lexical environment around native SQLBuild macros, enums, and constants. Use it to see what a resource can access, what it actually uses, why a declaration is visible or inaccessible, and whether a move would cross a scope boundary.

The command is read-only and offline. It does not connect to a warehouse, require warehouse credentials, or inspect relations. It reads the compiler-owned declaration-scope index and reuses a deterministic cache when the relevant source and configuration fingerprint has not changed. Building a cold cache uses the normal compiler expansion path, which loads the configured adapter and may execute authored Python macros; a warm cache hit reconstructs scope facts without importing macro modules.

Text output is deterministic, bounded, and requires no interactive pager.

### Usage

```bash
# Inspect an existing resource, declaration, or exact resource path
sqb scope TARGET [flags]

# Inspect the scope at a prospective file or directory
sqb scope --at PATH [flags]

# Preview moving an existing resource to a new path
sqb scope TARGET --as-path PATH [flags]
```

`TARGET` is either a kind-qualified identity or an exact project-relative resource path:

```bash
sqb scope model:stg_orders
sqb scope test:stg_orders__excludes_cancelled
sqb scope scenario:daily_revenue
sqb scope hook:grant_select
sqb scope function:normalize_status
sqb scope audit:positive_order_value
sqb scope source:raw__orders

sqb scope macro:normalize_order_status
sqb scope enum:order_status
sqb scope constant:minimum_order_value

sqb scope models/staging/orders/stg_orders.sql
```

Bare names such as `stg_orders` and `order_status` are rejected even if they are currently unique. Qualification keeps commands stable when names collide across resource or declaration kinds. Public declaration identities are `macro:<name>`, `enum:<name>`, and `constant:<name>`.

Model-private constants and enums include their owner in the introspection identity:

```text
enum:model:stg_orders._state
constant:model:stg_orders._minimum_value
```

These identities are for inspection. SQL authored inside the owning model continues to use `@enum("_state")` and `@const("_minimum_value")`.

### Flags

| Flag | Description |
|------|-------------|
| `--at PATH` | Inspect path-derived visibility for a prospective file or directory. A trailing `/` denotes a directory whose direct children are being considered. |
| `--as-path PATH` | Preview moving the existing target resource to `PATH`. No file or configuration is changed. |
| `--browse PATH` | Show direct child declaration folders and recursive counts without listing declarations. |
| `--list PATH` | Recursively list declarations under one declaration folder. |
| `--defined-under PATH` | Keep declarations whose definitions are under the project-relative path. |
| `--kind KIND` | Keep `macro`, `enum`, or `constant` declarations. Repeat to include multiple kinds. |
| `--match GLOB` | Match declaration names or qualified identities with a deterministic, case-sensitive glob. |
| `--used-only` | Keep declarations used by the target. |
| `--include-nearby` | Include bounded nearby declarations that are unavailable to the target. |
| `--nearby-depth N` | Set filesystem proximity for nearby descendant and sibling discovery (default: `1`). |
| `--dependency-depth N` | Expand dependencies from declarations in the used section by `N` edges (default: `0`). |
| `--explain QUALIFIED_NAME` | Explain one qualified declaration in detail at the target. |
| `--globals POLICY` | Control global declarations in the main report: `summary` (default), `used`, or `all`. |
| `--page-size N` | Return at most `N` declarations per paged section (default: `100`). |
| `--after CURSOR` | Continue after a declaration identity returned as the previous section's next cursor. |
| `--paths MODE` | Render paths as `relative`, `compact`, or `none`. |
| `--json` | Write the canonical versioned JSON report instead of the text tree. |

Filters combine in a fixed order: definition path, kind, glob, then usage. `--dependency-depth`
expands the filtered used declarations afterward. Parent-folder visibility is never depth-limited:
every unprefixed declaration role above the resource contributes to its scope.

### Reading A Report

The default text report keeps distinct facts in distinct sections:

- **Available** contains declarations visible through the resource's own lexical path.
- **Used** contains declarations consumed by the resource, including tracked declaration dependencies.
- **Relationship grants** contains eligible file-based enums and constants made available through expected-output sections in a test or scenario.
- **Nearby unavailable** is opt-in and explains close declarations that are outside the target's scope.
- **Scope chain** starts with the resource's owner folder, then shows parent folders and the project
  declaration roles. Its compact labels identify the access rule checked at each path.

Ordinary text rows show each declaration's qualified identity, definition location, visibility,
reason for appearing, declaration-role root, and safe type or signature metadata where useful.
`--explain` additionally shows its owning path, narrowest required placement, current consumers,
dependencies, and the consumers affected by a placement mismatch. JSON includes the complete
structured declaration report.

#### See the whole scope at once

Suppose orders and returns models use a macro published from their shared `commerce` folder, and
that macro composes two project-wide macros:

```text
project/
├── macros/
│   └── currency.py                 add_tax, round_money
└── models/
    └── commerce/
        ├── macros/
        │   └── orders.py           formatted_order_total
        ├── orders.sql
        └── returns/
            └── returns.sql
```

```python
# models/commerce/macros/orders.py
from macros.currency import add_tax, round_money

def formatted_order_total(expression: str) -> str:
    return round_money(add_tax(expression))
```

```sql
-- models/commerce/orders.sql
MODEL();

SELECT @formatted_order_total("subtotal") AS total
```

`returns/returns.sql` calls the same macro, so the declaration must remain available throughout
`models/commerce/` and its descendants.

The default report puts actual usage next to the complete directory-derived scope. Unused globals
stay collapsed, so the useful facts remain visible even in a large project:

```console
$ sqb scope model:orders
Scope
  Target: model:orders
  Resource: model:orders
  Path: models/commerce/orders.sql

Used (1)
  └─ ● macro:formatted_order_total  [macro; descendant-public; inherited_ancestor; params 1; role models/commerce/macros]  models/commerce/macros/orders.py:5:1

Scope chain
  ├─ exact-owner-private models/commerce (1)
  ├─ descendant-public models (0)
  └─ project global (2)

Available (1 of 3, 2 collapsed)
  └─ ● macro:formatted_order_total  [macro; descendant-public; inherited_ancestor; params 1; role models/commerce/macros]  models/commerce/macros/orders.py:5:1
  … 2 globals collapsed; run sqb scope model:orders --globals all

Relationship grants (0 of 0)
  (none)

Nearby unavailable (0 of 0)
  (none)

Diagnostics (0)
  (none)
Completeness: complete
```

This answers several questions without opening declaration files: what the model actually uses,
where that declaration came from, which owner and parent folders SQLBuild checks, how many
project-wide declarations are available, and whether the result is complete. The scope-chain count
at `models/commerce` includes declarations owned there; the `exact-owner-private` chain label does
not mean every declaration in that count is private.

#### Follow composed macro dependencies

`Used` is direct by default. Add `--dependency-depth` to follow declarations used by those
declarations. In this example, the model calls `formatted_order_total`, whose Python body calls
`add_tax` and `round_money`:

```console
$ sqb scope model:orders --used-only --dependency-depth 1
Scope
  Target: model:orders
  Resource: model:orders
  Path: models/commerce/orders.sql

Used (3)
  ├─ ● macro:add_tax  [macro; project; dependency; params 1; role macros]  macros/currency.py:1:1
  ├─ ● macro:formatted_order_total  [macro; descendant-public; inherited_ancestor; params 1; role models/commerce/macros]  models/commerce/macros/orders.py:5:1
  └─ ● macro:round_money  [macro; project; dependency; params 1; role macros]  macros/currency.py:5:1
```

The remaining report sections follow the `Used` section as usual. The dependency graph comes from
actual Python calls, including nested calls and calls reached through private helpers. Merely
importing a macro does not make it used. Increase the depth to follow longer chains.

Explain the composed macro to inspect its direct graph and placement facts:

```console
$ sqb scope model:orders --explain macro:formatted_order_total
Explanation
  └─ ● macro:formatted_order_total  [macro; descendant-public; inherited_ancestor; params 1; role models/commerce/macros]  models/commerce/macros/orders.py:5:1
     Owner: (none)
     Owning path: models/commerce
     Consumers: model:orders, model:returns
     Dependencies: macro:add_tax, macro:round_money
     Grants: (none)
     Required scope: descendant-public
     Required path: models/commerce
     Promotion impact: (none)
```

The complete command also prints the ordinary report sections above the `Explanation` section.
Use `--json` when another tool needs the same graph and placement facts as structured data.

Global declarations are an intentional project-wide API and can be numerous. The default `--globals summary` always retains globals used by the target but collapses the unused global inventory with exact counts. Use `--globals used` for only used globals or `--globals all` when a bounded full list is appropriate.

```bash
# Include every global declaration in the paged report
sqb scope model:stg_orders --globals all

# Focus on constants and enums defined in finance
sqb scope model:stg_orders \
  --kind constant \
  --kind enum \
  --defined-under models/finance

# Find visible or used settlement declarations
sqb scope model:stg_orders --match '*settlement*'
sqb scope model:stg_orders --used-only
```

### Expected-output access

Tests and scenarios have two independent ways to reach declarations. Their own folder paths provide
ordinary visibility. Each explicit `__expected__<model>` section adds the eligible file-based enums
and constants available to that model. This includes exact-folder `_enums/` and `_constants/`
declarations, despite their private visibility label.

`sqb scope` reports this additional access separately under **Relationship grants** and names the
model that provides it. With multiple expected models, SQLBuild makes the deterministic union of
their eligible declarations available while compiling the whole test or scenario. It never includes
macros or declarations defined inside a model's `MODEL()` header. A test filename, mirrored path,
or mock does not provide this access by itself.

```bash
sqb scope test:orders__completed_only
sqb scope scenario:daily_revenue --used-only
```

### Nearby And Explain

Nearby discovery is deliberately opt-in and bounded. It considers relevant declarations in the
same authored resource tree, parent folders, close neighboring branches and child folders, and
folders connected through expected-output relationships. It does not dump every private
declaration in the project.

```bash
# Find declarations just outside the model's effective scope
sqb scope model:stg_orders --include-nearby

# Include descendants and siblings two directory levels away
sqb scope model:stg_orders --include-nearby --nearby-depth 2

# Explain one declaration's visibility and placement at this model
sqb scope model:stg_orders --explain enum:customer_status
```

An explanation distinguishes a known but unavailable declaration from an unknown name. It reports
where the declaration is defined, why it is or is not available, which files use it, access through
expected output, required placement, and consumers affected by a placement mismatch. It does not
move or rewrite the declaration.

`--dependency-depth` is separate from `--nearby-depth`: it follows tracked declaration dependencies from the used section rather than filesystem proximity.

```bash
sqb scope model:stg_orders --used-only --dependency-depth 2
```

### Prospective Paths

Use `--at` before creating a resource. A prospective file receives the declarations implied by that exact authored path. A prospective directory describes what a direct child resource would receive.

```bash
sqb scope --at models/staging/orders/new_model.sql
sqb scope --at tests/unit/staging/orders/
```

The path must be project-relative, below a configured authored resource root, and use the appropriate resource suffix (`.sql`, or `.yml`/`.yaml` for sources). Paths outside those roots produce a diagnostic rather than borrowing scope from a nearby directory.

Prospective reports are intentionally partial: static path visibility is available, but runtime
usage and expected-output relationships do not exist yet. The report marks those sections
incomplete and exits nonzero while preserving the useful static result.

### Move Preview

`--as-path` calculates the visibility delta for moving one existing resource. It reports retained,
gained, and lost declarations; direct usages that the move would invalidate; the new resource-tree
root; declarations private to the resource's owner folder; and expected-output access retained
independently of folder visibility.

```bash
sqb scope model:stg_orders \
  --as-path models/marts/orders/stg_orders.sql
```

The destination must be a valid project-relative file path for that resource kind. This is a pure preview: `sqb scope` never moves files, edits declarations, or changes configuration.

### Folder Browsing

Browse and list are separate so a project with 10,000 or more declarations remains safe to explore. `--browse` returns only direct child declaration folders. Each folder has exact recursive declaration, usage, and kind counts plus its direct child-folder count; no arbitrary alphabetical prefix of declarations is printed.

Global roots appear in the browse namespace as `global/macros`, `global/constants`, and `global/enums`, regardless of how files are organized recursively beneath the top-level declaration roots.

```bash
# Start with folder summaries only
sqb scope model:stg_orders --browse .

# Walk down without listing declarations
sqb scope model:stg_orders --browse global
sqb scope model:stg_orders --browse global/macros/finance

# List declarations only after choosing a bounded domain
sqb scope model:stg_orders --list global/macros/finance/payments
```

`--list` is recursive and supports `--kind`, `--match`, `--defined-under`, `--used-only`, `--page-size`, and `--after`. Browse output itself stays folder-first.

### Pagination

Flat lists and report sections use qualified declaration identities as stable lexical cursors, not page numbers. In canonical JSON, every paged section reports its total, returned count, completeness, truncation state, and `next_cursor`. Repeat the same command and filters with that identity as `--after`:

```bash
# First page
sqb scope model:stg_orders \
  --list global/macros/legacy \
  --page-size 50

# Continue with the next_cursor from the first result
sqb scope model:stg_orders \
  --list global/macros/legacy \
  --page-size 50 \
  --after macro:legacy_batch_0049
```

Keep all semantic filters unchanged while continuing. Qualified cursors avoid cross-kind ambiguity. A bare cursor is accepted only when it resolves uniquely; invalid or ambiguous cursors produce a diagnostic and nonzero status rather than silently selecting a different page.

For automation, read each section's `next_cursor` from JSON and continue until it is `null`:

```bash
sqb scope model:stg_orders \
  --list global/macros/legacy \
  --page-size 50 \
  --json > scope-page.json
```

### Paths And JSON

`--paths relative` shows normalized project-relative paths. `compact` shortens repeated path context
in text output. `none` omits declaration definition locations and replaces structural and header
paths with `(hidden)`. Paths in stable machine output never expose an absolute workspace root.

`--json` emits the canonical schema rather than serializing the visual tree. The top-level `schema_version` is currently `1`. Reports include the target, scope chain, declaration sections, applied filters, section totals, collapsed and truncated flags, cursors, diagnostics, and aggregate and section-level completeness. Move previews and explanations appear when requested.

JSON is deterministically ordered, ASCII, newline-terminated, and byte-stable for identical inputs. It contains no ANSI formatting. Consumers should check `schema_version` before relying on fields.

### Partial Projects

Scope inspection remains useful while a project is broken. SQLBuild retains valid facts and marks
affected report sections complete or incomplete. Text and JSON never present a partial section as
complete, and diagnostics identify faults that prevented the missing facts from being indexed.

Diagnostics are stable and include project-relative source locations when available. A partial result, invalid target or cursor, or any error diagnostic produces a nonzero exit status after the available report is written. This lets an editor or agent consume path visibility while still treating incomplete analysis as a failed check.

### Output Safety

Scope reports describe declarations without exposing authored values or runtime secrets:

- Constants show logical type, nullability, collection kind, item count, and rendering mode, not values.
- Enums show scalar type, member count, and a bounded preview of member names, not member values.
- Macros show parameters and tracked declaration dependencies, not source bodies, callables, or source digests.
- Credentials, connection fields, environment variables, warehouse data, and absolute machine paths are not inspected or emitted.

There is no `--show-values` option.

### Native SQLBuild Only

`sqb scope` inspects native SQLBuild authored resources and declarations. It does not discover or emulate dbt models, dbt or Jinja macros, package dispatch, dbt manifests, dbt selectors, dbt tests, or dbt schema YAML visibility. An external dbt graph dependency does not contribute declarations or lexical scope.

For declaration directory rules, placement checks, test access through expected output, and scoped
macro imports, see [Declarations and Scopes](/concepts/declaration-scopes).

## kata

Source: `cli/kata.mdx`

Run configured SQL architecture checks, inspect rules, and generate policy guidance.

## sqb kata

Compiles the project and applies its configured [Kata architecture policy](/concepts/kata)
to compiled models. Built-in checks run offline and never connect to the warehouse or rewrite SQL.
Kata reports coded, error-only faults with source locations and remediations. Repository-defined
custom rules run in a bounded Python subprocess.

### Usage

```bash
sqb --project-dir <path> kata [flags]
sqb kata rule <rule-code>
sqb kata skills [--check]
```

### Evaluation flags

| Flag | Description |
|------|-------------|
| `--json` | Emit structured JSON instead of text |
| `--select`, `-s` | Evaluate selected models using normal SQLBuild selector syntax |
| `--exclude` | Exclude models from a non-empty `--select` scope |

Rule policy comes from `[kata].select` in `sqlbuild_project.toml`; CLI `--select` and `--exclude`
scope models within that policy. Model selectors support names, `tag:`, `path:`, graph `+`, and
path-between syntax.

`--exclude` is applied only when `--select` is also provided. To evaluate all models except one,
start with an explicit broad selector such as `--select path:models`.

### Text output

A clean policy prints its model and cache counts:

```text
Kata passed: 42 models evaluated, 0 faults (40 cache hits, 2 misses)
```

Faults include a source location, rule code, message, and remediation. Model-level checks use
line 1, column 1:

```text
models/mart/orders.sql:1:1 [SQBKS001] model SQL must keep transformation logic in top-level CTEs
  Remediation: Move transformation logic into named top-level CTEs before the terminal SELECT.
Found 1 kata faults
```

Project-phase SQL test policy also reports the authored test or scenario path. A finding can name
the compiler-resolved target and exact destination:

```text
tests/unit/test_stg_orders.sql:1:1 [SQBKT003] unit test block 1 resolves to resources mirrored by tests/unit/staging/
  Remediation: Move this test file beneath tests/unit/staging/.
Found 1 kata faults
```

`SQBKT` rules run once per project, including projects with direct-resource tests but no models.
Path-scoped exceptions and ignores match the reported test or scenario path.

### JSON output

```bash
sqb kata --json
```

```json
{
  "cache_hits": 0,
  "cache_misses": 1,
  "evaluated_models": 1,
  "fault_count": 1,
  "faults": [
    {
      "code": "SQBKS001",
      "column": 1,
      "line": 1,
      "message": "model SQL must keep transformation logic in top-level CTEs",
      "path": "models/mart/orders.sql",
      "remediation": "Move transformation logic into named top-level CTEs before the terminal SELECT."
    }
  ]
}
```

Faults are ordered deterministically by path, position, code, and content.

### Inspect a rule

`rule` prints metadata for any exact built-in or configured custom code. The rule does not need to
be active:

```bash
sqb kata rule SQBKS101
```

```text
SQBKS101: dependency-import-ctes
Family: structure
Enabled by default: no
Kind: built-in

dependencies must be isolated in import CTEs

Remediation: Move each __ref(...) or __source(...) into one named top-level import CTE and reference that CTE from later logic.
```

Custom rules also show their source and declared option defaults.

Inspecting an `SQBKT` rule also prints the effective canonical roots and configured cross-domain
pipeline directory:

```bash
sqb kata rule SQBKT003
```

### Generate policy skills

Generate agent guidance from the active rules, options, thresholds, naming vocabulary, SQL test
paths, and scoped deviations:

```bash
sqb kata skills
```

Kata writes the same policy-specific guidance to:

- `.agents/skills/sqlbuild-kata/SKILL.md`
- `.claude/skills/sqlbuild-kata/SKILL.md`
- `.opencode/skills/sqlbuild-kata/SKILL.md`

Check committed guidance in CI without rewriting it:

```bash
sqb kata skills --check
```

Install mode refuses to overwrite divergent, malformed, or unowned files. See
[SQLBuild skills](/cli/skills) for the separate general framework guidance command.

### Exit codes

| Command | Code | Meaning |
|---------|------|---------|
| `sqb kata` | `0` | No retained faults |
| `sqb kata` | `1` | Faults found or Kata could not evaluate the project |
| `sqb kata rule` | `0` | Exact rule found |
| `sqb kata rule` | `2` | Unknown rule code |
| `sqb kata skills` | `0` | Guidance installed |
| `sqb kata skills --check` | `0` | All guidance is fresh |
| `sqb kata skills --check` | `1` | Guidance is not fresh: missing, stale, divergent, malformed, or unowned |

### Examples

```bash
# Evaluate the configured policy
sqb kata

# Emit machine-readable CI output
sqb kata --json

# Scope evaluation to marts and their downstream models
sqb kata --select tag:marts+

# Inspect an opt-in rule before adopting it
sqb kata rule SQBKJ002

# Keep policy-derived agent guidance current
sqb kata skills
sqb kata skills --check
```

## plan

Source: `cli/plan.mdx`

Preview what SQLBuild will do before executing.

## sqb plan

Shows the execution plan without making any changes. Useful for inspecting change detection, backfill policies, and selector scope before building.

### Usage

```bash
sqb --project-dir <path> plan [flags]
```

### Flags

| Flag | Description |
|------|-------------|
| `--no-sql-validation` | Skip compile-time SQL syntax validation |
| `--changes-only` | Narrow the plan to only stale models; prune anything already current (virtual environments only) |
| `--no-python` | Exclude read-side Python tasks and assets from the plan |
| `--defer-to` | Resolve unselected model references against another target |
| `--json` | Output the plan as JSON |
| `--full-refresh` | Plan a full rebuild for selected models unless a model sets `full_refresh false`; `full_refresh true` forces a model without this flag |
| `--start-cursor-ts` | Override start cursor for timestamp incremental models (ISO format) |
| `--end-cursor-ts` | Override end cursor for timestamp incremental models (ISO format) |
| `--start-cursor-int` | Override start cursor for integer incremental models |
| `--end-cursor-int` | Override end cursor for integer incremental models |
| `--select`, `-s` | Select specific models |
| `--exclude` | Exclude specific models |

### Output

First run:

```
Plan ready (13 selected)

First run (12)
  stg_customers               view
  stg_payments                view
  stg_orders                  view
  daily_order_partitioned     partition_tracked (custom)
  daily_revenue               table
  dim_customers               table
  fact_orders                 table
  customer_status_snapshot    merge (timestamp)
  hourly_order_activity       delete_insert (timestamp, microbatch)
  daily_activity_rollup       delete_insert (timestamp, microbatch)
  hourly_activity_with_daily_context delete_insert (timestamp, microbatch)
  order_status_index          delete_insert (integer)

Seeds (1)
  waffle_types
```

Steady state:

```
Plan ready (13 selected)

Normal (12)
    3 view
    3 table
    3 delete_insert (timestamp, microbatch)
    1 partition_tracked (custom)
    1 merge (timestamp)
    1 delete_insert (integer)

Seeds (1)
  waffle_types
```

When query or schema changes are detected, the plan shows the affected models with backfill actions and cascade information.

### Missing upstream dependencies

Planning a scoped selection whose upstream inputs were never built in the target fails with `S301` rather than producing a plan that would break at build time:

```
error[S301]: cannot build selected scope: 3 missing upstream dependencies (stg_orders, stg_payments, waffle_types)
```

Build the upstream chain first, or select it along with the model: `sqb build --select +fact_orders`.

## build

Source: `cli/build.mdx`

Execute the build lifecycle: compile, plan, and build what changed.

## sqb build

Compiles, plans, and executes the build lifecycle. By default, SQLBuild runs your full selection. In a [virtual environment](/concepts/virtual-environments), pass `--changes-only` (or set `changes_only = true` in config) to skip work that is already current - unchanged models, seeds, audits, and Python nodes. Use `--no-tests` and `--no-audits` to skip validation for fast iteration.

### Usage

```bash
sqb --project-dir <path> build [flags]
```

### Flags

| Flag | Description |
|------|-------------|
| `--target` | Build against a configured target instead of the active/default target |
| `--changes-only` | Skip models, seeds, audits, and Python nodes that are already current; build only stale work (virtual environments only) |
| `--no-tests` | Skip SQL unit tests |
| `--no-audits` | Skip audits |
| `--no-python` | Skip read-side Python tasks and assets (loader-side Python still runs for selected sources) |
| `--no-sql-validation` | Skip compile-time SQL syntax validation |
| `--full-refresh` | Drop and rebuild selected models unless a model sets `full_refresh false`; `full_refresh true` forces a model even without this flag |
| `--defer-to` | Resolve unselected model references against another target |
| `--defer-sources-to` | Read managed source data from another target |
| `--fail-fast` | Stop on first failure and skip remaining nodes |
| `--concurrency` | Number of worker connections (default: 1) |
| `--verbose`, `-v` | Show lifecycle SQL inline after each model |
| `--start-cursor-ts` | Override start cursor for timestamp incremental models (ISO format) |
| `--end-cursor-ts` | Override end cursor for timestamp incremental models (ISO format) |
| `--start-cursor-int` | Override start cursor for integer incremental models |
| `--end-cursor-int` | Override end cursor for integer incremental models |
| `--load` | Explicitly load managed sources before building |
| `--no-load` | Skip automatic source loading |
| `--reload` | Reload managed sources (passes `is_reload=True` to loaders) |
| `--include-stale-upstreams` | Expand selection to include stale upstream models needed for coherence |
| `--manifest` | Generate `target/manifest.json` with plan-aware project metadata |
| `--select`, `-s` | Select specific models |
| `--exclude` | Exclude specific models |

### Fast iteration

Use `--no-tests` and `--no-audits` to skip validation when you only want to materialize models:

```bash
sqb build --no-tests --no-audits
```

This replaces the former `sqb run` command. The full lifecycle (tests + audits) is always the default; skip flags opt out of specific phases when you need speed.

### Execution order

1. Managed sources are loaded (unless `--no-load`)
2. Seeds are loaded (if changed)
3. Source audits run before their dependent models (unless `--no-audits`)
4. SQL unit tests run before their target model (unless `--no-tests`)
5. Models are materialized in DAG topological order (`--changes-only` skips models already current)
6. Error-severity audits run against the staging table before promotion to the target (unless `--no-audits`)

### Output

```
Execution  sqb build  (concurrency: 1)

   1/13  seed      waffle_types                                          OK     0.09s
   2/13  view      stg_customers                                         OK     0.05s
           audit     not_null (customer_id)                              PASS
           audit     unique (customer_id)                                PASS
   3/13  view      stg_orders                                            OK     0.03s
           test      test_stg_orders                                     PASS
           audit     not_null (order_id)                                 PASS
           audit     unique (order_id)                                   PASS
  10/13  table     hourly_order_activity  (delete_insert)                OK     0.16s
           audit (d) expression_is_true                                  PASS  4/4
           audit (d) not_null (activity_hour)                            PASS  4/4
           audit (f) expression_is_true                                  PASS
           audit (f) not_null (activity_hour)                            PASS

Completed successfully.
PASS=66  WARN=0  FAIL=0  SKIP=0  TOTAL=66  (1.09s)
```

### Deferred builds

Use `--defer-to` to resolve unselected model references against another target. This lets you build a subset of models in dev while referencing production tables for everything else:

```bash
sqb build --select fact_orders --defer-to prod
```

No `manifest.json` is required. `--defer-to` selects only the namespace used for unselected
references. SQLBuild resolves those relations through the active target's sole physical
connection and never opens the deferred target's connection. The deferred namespace must be
visible and readable through the active connection; deferral is not a cross-account,
cross-server, or cross-file transfer mechanism.

### Failure behavior

When a model fails:
- Downstream models are automatically blocked and skipped
- Staging/delta tables are retained for inspection
- Failure details show the model name, failed phase, and error message

### Fingerprints

After a successful build, SQLBuild writes version identities to `_sqlbuild_fingerprints` in the target schema. These are used on subsequent runs to detect changes and skip unchanged work. See [Planning and Change Detection](/concepts/planning) for details.

### Runtime artifacts

Build writes executed lifecycle SQL to `target/run/models/`. These files contain the actual SQL that was executed, including resolved cursor bounds and runtime substitutions.

## load

Source: `cli/load.mdx`

Load managed sources into the warehouse.

## sqb load

Runs source loader functions and writes data into their target tables using the configured write strategy.

### Usage

```bash
sqb --project-dir <path> load [flags]
```

### Flags

| Flag | Description |
|------|-------------|
| `--select`, `-s` | Select specific sources or loaders by name |
| `--exclude` | Exclude specific sources or loaders |
| `--reload` | Pass `is_reload=True` to loader functions |
| `--concurrency` | Number of worker connections (default: from settings or 1) |
| `--start-cursor-ts` | Override start cursor for timestamp-based loaders (ISO format) |
| `--end-cursor-ts` | Override end cursor for timestamp-based loaders (ISO format) |
| `--start-cursor-int` | Override start cursor for integer-based loaders |
| `--end-cursor-int` | Override end cursor for integer-based loaders |
| `--json` | Output results as JSON |
| `--json-output` | Write JSON results to a file path |
| `--var` | Set project variables (`--var key=value`) |

### Examples

```bash
# Load all managed sources
sqb load

# Load a specific source
sqb load --select raw_customers

# Load with concurrency
sqb load --concurrency 4

# Reload all sources (full refresh behavior)
sqb load --reload

# Override cursor bounds
sqb load --start-cursor-ts "2026-05-01T00:00:00"
```

### Execution order

Loaders are executed in DAG topological order based on `depends_on` declarations. Independent loaders run concurrently when `--concurrency` is greater than 1.

Intermediate loaders (those referenced only via `depends_on` without a direct source binding) run first, followed by the source-bound loaders that depend on them.

### Output

```
Load ready (3 selected)

Sources (3)
  raw_customers
  raw_orders
  raw_payments

Execution  sqb load  (concurrency: 1)

  1/3  source    raw_customers                  OK     0.05s  rows=5
  2/3  source    raw_orders                     OK     0.03s  rows=10
  3/3  source    raw_payments                   OK     0.02s  rows=8

Completed successfully.
PASS=3  WARN=0  FAIL=0  SKIP=0  TOTAL=3  (0.12s)
```

### Auto-load during builds

`sqb build` automatically loads managed sources before building dependent models. This is controlled by the `auto_load_sources` setting (default: `true`) and the `--load` / `--no-load` / `--reload` flags:

```bash
# Default: auto-load is on
sqb build

# Explicitly skip loading
sqb build --no-load

# Force reload
sqb build --reload
```

See [Loaders](/concepts/python-nodes/loaders) for full documentation on write strategies, the loader context API, and source deferral.

## seed

Source: `cli/seed.mdx`

Load seed CSV files into the warehouse.

## sqb seed

Loads seed CSV files into the warehouse as tables. Seeds are fully replaced on every run.

### Usage

```bash
sqb --project-dir <path> seed [flags]
```

### Flags

| Flag | Description |
|------|-------------|
| `--select`, `-s` | Select specific seeds by name |
| `--exclude` | Exclude specific seeds |

### Examples

```bash
# Load all seeds
sqb seed

# Load a specific seed
sqb seed --select seed:waffle_types
```

## test

Source: `cli/test.mdx`

Run SQL unit tests and multi-model tests in isolation.

## sqb test

Runs SQL unit tests, independently reported parameterized cases, and multi-model tests without
building models. Useful for validating test logic independently.

### Usage

```bash
sqb --project-dir <path> test [flags]
```

### Flags

| Flag | Description |
|------|-------------|
| `--no-sql-validation` | Skip compile-time SQL syntax validation |
| `--select`, `-s` | Select tests targeting specific models |
| `--exclude` | Exclude tests targeting specific models |

Parameterized cases use parent-level selection. Selecting a target model includes every case in
each matching `TEST` template; case names are not model selectors.

Text output identifies each case as `<parent> [<case>]` and includes its source path and safe typed
parameters. Structured JSON emits one check per case with stable source/block/case identity,
declared parameter types and nullability, typed values, and a content fingerprint. Exact decimals
are strings in JSON so their scale is preserved.

### Examples

```bash
# Run all tests
sqb test

# Run tests for a specific model
sqb test --select stg_orders
```

## scenario

Source: `cli/scenario.mdx`

Run end-to-end scenario tests against the warehouse or locally with DuckDB.

## sqb scenario

Run end-to-end scenario tests. Scenarios materialize fixture inputs as physical relations, build the real project graph against them, and evaluate expected outputs and assertions. See [Scenarios](/concepts/scenarios) for concepts and authoring details.

### sqb scenario test

Run scenario tests against the warehouse.

```bash
sqb scenario test [flags]
```

#### Flags

| Flag | Description |
|------|-------------|
| `--select`, `-s` | Select scenarios to run |
| `--exclude` | Exclude scenarios from the selection |
| `--retain` | Keep scenario-owned warehouse artifacts for inspection |
| `--local` | Run locally against DuckDB using captured JSONL snapshots |
| `--strict` | Treat missing/stale local snapshots as errors instead of skips |
| `--sync-snapshots` | Capture missing/stale snapshots before local run (requires `--local`) |
| `--refresh` | Recapture all selected snapshots before local run (requires `--local`) |
| `--force` | Bypass snapshot capture safety limits |
| `--max-snapshot-rows` | Override per-relation row limit for capture |
| `--max-snapshot-total-rows` | Override total row limit for capture |
| `--max-snapshot-bytes` | Override per-relation byte limit for capture |
| `--max-snapshot-total-bytes` | Override total byte limit for capture |
| `--no-sql-validation` | Skip compile-time SQL syntax validation |

#### Selectors

Scenarios are selected with `--select`. `--exclude` removes scenarios from the selection. Without any selectors, all discovered scenarios run.

| Selector | Example |
|----------|---------|
| Scenario name | `sqb scenario test --select daily_revenue_minimal` |
| Multiple names | `sqb scenario test --select daily_revenue_minimal --select daily_revenue_multi_order` |
| `.sql` file path | `sqb scenario test --select tests/scenarios/revenue/daily_revenue_minimal.sql` |
| Folder | `sqb scenario test --select tests/scenarios/revenue` |
| Scenario-root-relative folder | `sqb scenario test --select revenue` |
| Exclude | `sqb scenario test --select revenue --exclude daily_revenue_multi_order` |

Mixed selector types are supported and the result is de-duplicated by scenario name.

#### Remote examples

```bash
# Run all scenarios
sqb scenario test

# Run one scenario
sqb scenario test --select daily_revenue_minimal

# Run and retain warehouse artifacts
sqb scenario test --select daily_revenue_minimal --retain

# Run all scenarios in a folder
sqb scenario test --select revenue
```

#### Local examples

```bash
# Run locally (requires prior capture)
sqb scenario test --local

# Run locally, capture missing/stale snapshots first
sqb scenario test --local --sync-snapshots

# Run locally, recapture everything first
sqb scenario test --local --refresh

# Fail on missing/stale snapshots instead of skipping
sqb scenario test --local --strict
```

#### Output

Remote scenarios report per-scenario PASS/FAIL with nested check rows:

```
daily_revenue_minimal                                            PASS
    check     expected daily_revenue                             PASS
    check     assertion no_negative_revenue                      PASS

PASS=1  FAIL=0  TOTAL=1
```

Local scenarios add ERROR and SKIP statuses:

```
PASS=2  FAIL=0  ERROR=0  SKIP=1  TOTAL=3
```

Failed scenarios suggest rerunning with `--retain` for inspection. Local runs always keep the DuckDB file at `target/run/scenarios/<scenario_name>/local.duckdb`.

### sqb scenario capture

Capture scenario input fixtures from the warehouse as JSONL snapshots for local replay.

```bash
sqb scenario capture [flags]
```

#### Flags

| Flag | Description |
|------|-------------|
| `--select`, `-s` | Select scenarios to capture |
| `--exclude` | Exclude scenarios from the selection |
| `--retain` | Keep warehouse fixture artifacts after capture |
| `--force` | Bypass snapshot capture safety limits |
| `--max-snapshot-rows` | Override per-relation row limit |
| `--max-snapshot-total-rows` | Override total row limit |
| `--max-snapshot-bytes` | Override per-relation byte limit |
| `--max-snapshot-total-bytes` | Override total byte limit |
| `--no-sql-validation` | Skip compile-time SQL syntax validation |

#### Examples

```bash
# Capture all scenarios
sqb scenario capture

# Capture one scenario
sqb scenario capture --select daily_revenue_minimal

# Capture and retain warehouse artifacts
sqb scenario capture --select daily_revenue_minimal --retain
```

Snapshots are written to `tests/_scenario_snapshots/<scenario_name>/` with a `scenario.json` manifest and JSONL files for each fixture relation. These files can be committed to version control.

### Runtime artifacts

Both remote and local scenario runs write runtime artifacts to `target/run/scenarios/<scenario_name>/`:

```
target/run/scenarios/daily_revenue_minimal/
  cleanup/
    prepare.sql
    final.sql
  fixtures/
    ref__stg_orders.sql
    ref__stg_payments.sql
  models/
    marts/daily_revenue.sql
  checks/
    expected__daily_revenue.sql
    assertion__no_negative_revenue.sql
```

Local runs additionally write to a `local/` subdirectory and create `local.duckdb`.

## audit

Source: `cli/audit.mdx`

Run data quality audits in isolation.

## sqb audit

Runs all attached audits without rebuilding models. Useful for verifying data quality on existing warehouse state.

### Usage

```bash
sqb --project-dir <path> audit [flags]
```

### Flags

| Flag | Description |
|------|-------------|
| `--no-sql-validation` | Skip compile-time SQL syntax validation |
| `--defer-to` | Resolve model references against another target |
| `--select`, `-s` | Select audits attached to specific models |
| `--exclude` | Exclude audits attached to specific models |
| `--concurrency` | Maximum number of audits to run concurrently (default: `1`) |

### Concurrency

Standalone audits run serially by default. Use `--concurrency` to opt into parallel warehouse
queries:

```bash
sqb audit --concurrency 8
```

SQLBuild resolves the limit in this order: an explicit `--concurrency` value, the
`SQLBUILD_CONCURRENCY` environment variable, the effective project `settings.concurrency`, then
the product default of `1`. Values must be at least `1`.

The physical worker count is bounded by the number of selected audits. Each active worker opens
and exclusively uses one warehouse connection, so higher concurrency can increase warehouse load
and cost. Results and final JSON remain in plan order even when queries finish in a different
order.

If an audit query raises a runtime, adapter, or framework error, SQLBuild records that failure and
continues running the remaining independent audits. After all selected audits have been attempted,
it reports every query failure in plan order and exits nonzero. Failed queries do not produce
fabricated audit results.

Interruption and cancellation are different: SQLBuild stops scheduling new audits, drains queries
that have already started, and then closes every worker connection. Generic adapters cannot
guarantee immediate cancellation of a query already running in the warehouse.

### Examples

```bash
# Run all audits
sqb audit

# Run audits for marts only
sqb audit --select path:models/marts

# Run up to 8 audit queries concurrently
sqb audit --concurrency 8
```

## freshness

Source: `cli/freshness.mdx`

Observe source freshness without writing state.

## sqb freshness

Observes the current data version of each source and reports whether the data has changed since the last build. Does not write any state or trigger builds.

### Usage

```bash
sqb --project-dir <path> freshness [flags]
```

### Flags

| Flag | Description |
|------|-------------|
| `--state` | Compare observations against stored freshness state from the last build |
| `--fail-on-error` | Exit with code 1 if any source observation fails or is unknown |
| `--fail-on-stale` | Exit with code 1 if any source has changed, is unknown, or errored (requires `--state`) |
| `--virtual-env` | Read previous state from the specified virtual environment instead of direct state |
| `--json` | Output as JSON instead of human-readable text |
| `--json-output` | Write JSON output to a file path (also prints text to stdout unless `--json` is set) |
| `--no-sql-validation` | Skip compile-time SQL syntax validation |
| `--select`, `-s` | Select specific sources or models (sources upstream of selected models are included) |
| `--exclude` | Exclude specific sources or models |

### Source selection

Without `--select`, all sources in the project are observed. When `--select` is provided, selectors work like other commands: you can select sources by name, or select models and their upstream sources are automatically included:

```bash
# Observe all sources
sqb freshness

# Observe a specific source
sqb freshness --select raw_orders

# Observe sources upstream of a model
sqb freshness --select fact_orders
```

### Observation without state

By default, `sqb freshness` observes the current data version of each source and reports what it found. No comparison is made against previous observations:

```bash
sqb freshness
```

```
Source freshness

Observed (3)
  raw_customers  timestamp  2026-06-05T14:30:00  adapter
  raw_orders     timestamp  2026-06-05T15:45:00  column  tolerance 15m
  raw_payments   integer    42871                 column

Summary: observed=3 changed=0 unchanged=0 tolerated=0 unknown=0 errors=0
```

Sources without explicit `freshness:` config are auto-observed using the `adapter` strategy if the adapter supports table metadata. Sources that can't be observed (expression sources, managed sources without freshness config on unsupported adapters) show as `unknown`.

### Comparing against state

Use `--state` to compare current observations against the freshness state stored from the last successful build:

```bash
sqb freshness --state
```

```
Source freshness

Changed (1)
  raw_orders     previous 2026-06-05T12:00:00  current 2026-06-05T15:45:00  tolerance 15m

Unchanged (1)
  raw_customers  previous 2026-06-05T14:30:00  current 2026-06-05T14:30:00

Tolerated (1)
  raw_payments   previous 2026-06-05T14:28:00  current 2026-06-05T14:30:00  tolerance 15m

Summary: observed=0 changed=1 unchanged=1 tolerated=1 unknown=0 errors=0
```

#### Statuses

| Status | Meaning |
|--------|---------|
| `observed` | Successfully observed (no state comparison) |
| `changed` | Data version differs from the stored state |
| `unchanged` | Data version matches the stored state exactly |
| `tolerated` | Data version differs but is within the `lag_tolerance` threshold |
| `unknown` | No freshness config and adapter metadata unavailable, or no previous state to compare against |
| `error` | Observation failed (e.g. source table does not exist, query error) |

#### Virtual environment state

To compare against state stored in a virtual environment instead of direct mode state:

```bash
sqb freshness --state --virtual-env pr_123
```

### CI integration

Use `--fail-on-error` to fail the pipeline if any source can't be observed:

```bash
sqb freshness --fail-on-error
```

Use `--fail-on-stale` with `--state` to fail if any source has new data that hasn't been built yet:

```bash
sqb freshness --state --fail-on-stale
```

This is useful for CI gates that should block if source data has changed but the pipeline hasn't run yet.

### JSON output

```bash
sqb freshness --json
```

```json
{
  "sources": [
    {
      "name": "raw_orders",
      "status": "observed",
      "strategy": "column",
      "value_kind": "timestamp",
      "current_data_version": "2026-06-05T15:45:00",
      "previous_data_version": null,
      "lag_tolerance": "15m",
      "target": {
        "database": null,
        "schema": "raw",
        "name": "orders"
      },
      "message": null
    }
  ],
  "summary": {
    "observed": 1,
    "changed": 0,
    "unchanged": 0,
    "tolerated": 0,
    "unknown": 0,
    "errors": 0
  }
}
```

### See also

- [Sources: Source freshness](/concepts/sources#source-freshness) for freshness configuration
- [Planning and Change Detection](/concepts/planning) for how freshness feeds into change-aware builds

## check

Source: `cli/check.mdx`

Run Python checks against tasks, assets, and loaders.

## sqb check

Runs Python [checks](/concepts/python-nodes/checks) in isolation. Checks validate the output of tasks, assets, and loaders. For SQL relation validation, use [`sqb audit`](/cli/audit) instead.

### Usage

```bash
sqb --project-dir <path> check [flags]
```

### Flags

| Flag | Description |
|------|-------------|
| `--select`, `-s` | Select checks to run (by name, `check:`, `tag:`, or graph expansion) |
| `--exclude` | Exclude checks from the selection |
| `--no-sql-validation` | Skip compile-time SQL syntax validation |
| `--json` | Print check results as JSON |
| `--json-output` | Write check results JSON to a file path |
| `--vars` | Override project variables |

Selecting a non-check node is rejected; use [`sqb build`](/cli/build) to run tasks and assets.

### Examples

```bash
# Run all checks
sqb check

# Run one check and its required dependencies
sqb check --select +check_orders_exported

# Run checks by tag
sqb check --select tag:exports

# Print results as JSON
sqb check --json
```

### Output

Checks report PASS, FAIL, or WARN per check. A failing `error`-severity check exits non-zero; `warn`-severity failures are reported without failing the command.

Results are written to `target/run/checks/python_checks.json`.

### Relationship to build

`sqb build` runs relevant Python checks by default after the tasks, assets, and loaders they depend on have run. `sqb build --no-audits` skips checks alongside audits. `sqb check` runs only checks, on demand.

## clone

Source: `cli/clone.mdx`

Copy model relations between configured targets.

## sqb clone

Copies selected relations from one target to another. It uses adapter-native cloning where supported and physical copies where required; `--hard-copy` forces a physical copy on adapters that support both.

No `manifest.json` generation or artifact management is required. Clone works directly against live targets.

When `--to` is omitted, the destination is the active target selected by `--target`,
`sqlbuild_local.toml`, or `default_target`, in that order.

`--from` selects only the origin namespace and its clone-origin policy. `--to`, or the active
target when it is omitted, selects the sole physical connection used by the operation. The
origin namespace must therefore be visible and readable through the destination connection.
SQLBuild never resolves or opens the origin target's connection, including for direct,
deferred, and virtual clone. Clone cannot perform a cross-account, cross-server, or cross-file
transfer by opening a second connection.

### Usage

```bash
sqb --project-dir <path> clone --from <target> [--to <target>] [flags]
```

### Flags

| Flag | Description |
|------|-------------|
| `--from` | Source target (required) |
| `--to` | Destination target; defaults to the active target |
| `--hard-copy` | Force physical table copies instead of zero-copy cloning |
| `--no-sql-validation` | Skip compile-time SQL syntax validation |
| `--select`, `-s` | Select specific models to clone |
| `--exclude` | Exclude specific models from cloning |

### Examples

```bash
# Clone all models from prod to dev
sqb clone --from prod --to dev

# Equivalent when dev is the active target
sqb clone --from prod

# Clone only marts to dev
sqb clone --from prod --to dev --select path:models/marts

# Force physical copies
sqb clone --from prod --to dev --hard-copy
```

### Managed sources

Clone includes selected managed physical sources when the destination target reads its own
loader namespace. Sources are copied before seeds and models so views can be recreated in a
destination that has never been built.

Source locations respect target configuration:

- The origin relation comes from the target that the origin uses for managed source reads.
- The destination relation uses the destination target's `loader_schema`, falling back to
  its model `schema`.
- If the destination defers source reads to another target, clone reuses that target's source
  relation and does not copy or overwrite it.
- Expression sources and unmanaged external sources are not cloned.

`--hard-copy` controls how included relations are copied. It does not change which managed
sources are selected.

### Clone policies

Targets deny cloning by default. Enable the origin and destination explicitly in `sqlbuild_project.toml`:

```toml
[targets.prod.clone]
allow_as_clone_origin = true

[targets.dev.clone]
allow_as_clone_destination = true
```

The origin target must already contain the built relations being cloned. The destination
connection's credentials must be able to read the origin namespace and create relations in the
destination. Managed physical sources may bootstrap a destination that has not been built. See
[Project Configuration](/concepts/project-configuration) for details.

## diff

Source: `cli/diff.mdx`

Compare schemas and data between targets or virtual environments.

Compares schemas and optionally row-level data between two build contexts: two targets (e.g. `prod:dev`) in direct mode, or two virtual environments when virtual mode is enabled. See [Data Diffs](/concepts/diff) for detailed usage.

### Usage

```bash
sqb diff <FROM>:<TO> <mode> [flags]
```

The first argument is a positional `FROM:TO` range. Exactly one mode is required: `--full`, `--schema-only`, or `--bounded <duration>`.

In direct mode, `FROM` and `TO` are configured target names. Each target supplies its named
connection and authoritative database/schema namespace; invalid connection references are
reported as offline configuration errors.

Full and bounded row comparisons require the model to define `unique_key`. Bounded mode uses the model's cursor and falls back to a full row comparison when no cursor is configured.

### Flags

| Flag | Description |
|------|-------------|
| `--full` | Compare both schema and all row data |
| `--schema-only` | Compare column names and types only |
| `--bounded` | Compare row data within a recent window (e.g. `14d`, `6h`) |
| `--verbose`, `-v` | Show more example rows (default: 3, verbose: 10) |
| `--max-column-examples` | Override maximum examples per changed column |
| `--max-row-only-examples` | Override maximum examples for side-only rows |
| `--no-sql-validation` | Skip compile-time SQL syntax validation |
| `--select`, `-s` | Select specific models to diff (required in v1) |
| `--exclude` | Exclude specific models from diffing |

### Examples

```bash
# Full diff of a specific model
sqb diff prod:dev --full --select customer_status_snapshot

# Schema-only diff of all marts
sqb diff prod:dev --schema-only --select path:models/marts

# Bounded diff of last 14 days
sqb diff prod:dev --bounded 14d --select hourly_order_activity
```

### Exit codes

Returns `0` when all selected models have no differences, `1` when any model has schema or row differences.

## lineage

Source: `cli/lineage.mdx`

Explore model and column-level dependency graphs from the command line.

Inspect upstream and downstream dependencies for any model, source, seed, or function in your project. Supports both model-level lineage (dependency graph) and column-level lineage (tracing individual columns through transformations). Outputs as a tree, edge list, or structured JSON.

`sqb compile` computes lineage for validation and includes per-model summaries in its JSON report. Use this command when you need to inspect or export the actual lineage graph.

### Usage

```bash
# Model lineage: dependency graph around a single resource
sqb lineage <target> [flags]

# Column lineage: trace a specific column
sqb lineage <model>.<column> [flags]

# Selector mode: lineage for a selected scope
sqb lineage --select <selector> [flags]
```

Exactly one of a positional target or `--select` is required.

### Flags

| Flag | Description |
|------|-------------|
| `--direction` | `upstream` (default), `downstream`, or `both`. `both` is only available for model lineage. |
| `--depth` | How many hops to traverse. An integer or `all` (default: `all`). |
| `--format` | Output format: `tree` (default), `list`, or `json`. |
| `--mode` | Column lineage analysis mode: `rich` (default) or `fast`. |
| `--no-sql-validation` | Skip compile-time SQL syntax validation. |
| `--select`, `-s` | Select resources using standard selector syntax. |
| `--exclude` | Exclude resources from the selection. |

### Model lineage

When the target is a plain resource name, lineage shows the model-level dependency graph.

#### Tree

The default. Shows an indented dependency tree with resource types and file paths:

```bash
sqb lineage fact_orders --direction both
```

```
Lineage  model  fact_orders  models/marts/fact_orders.sql  both
upstream
├── model  stg_orders  models/staging/stg_orders.sql
│   └── source  raw__orders  sources/raw.yml
├── model  stg_payments  models/staging/stg_payments.sql
│   └── source  raw__payments  sources/raw.yml
├── seed  waffle_types  seeds/waffle_types.csv
└── function  udf__is_completed_order  functions/sql/udf__is_completed_order.sql
downstream
├── model  customer_status_snapshot  models/intermediate/customer_status_snapshot.sql
├── model  hourly_order_activity  models/marts/hourly_order_activity.sql
│   ├── model  daily_activity_rollup  models/marts/daily_activity_rollup.sql
│   │   └── model  hourly_activity_with_daily_context  models/marts/hourly_activity_with_daily_context.sql
│   │       └── model  hourly_order_activity  (already shown)
│   └── model  hourly_activity_with_daily_context  (already shown)
└── model  order_status_index  models/intermediate/order_status_index.sql
```

Cycles and repeated nodes are annotated with "(already shown)" to avoid infinite recursion.

#### List

An edge list showing each dependency as a directed pair:

```bash
sqb lineage fact_orders --format list
```

```
source:raw__orders    -> model:stg_orders
source:raw__payments  -> model:stg_payments
model:stg_orders     -> model:fact_orders
model:stg_payments   -> model:fact_orders
seed:waffle_types    -> model:fact_orders
```

#### JSON

Structured output with nodes, edges, and metadata:

```bash
sqb lineage fact_orders --format json
```

```json
{
  "nodes": [
    {
      "id": "model:fact_orders",
      "name": "fact_orders",
      "resource_type": "model",
      "relative_path": "models/marts/fact_orders.sql",
      "qualified_name": "dev.fact_orders"
    },
    {
      "id": "source:raw__orders",
      "name": "raw__orders",
      "resource_type": "source",
      "relative_path": "sources/raw.yml"
    }
  ],
  "edges": [
    {"from": "source:raw__orders", "to": "model:stg_orders"},
    {"from": "model:stg_orders", "to": "model:fact_orders"}
  ],
  "focus": ["model:fact_orders"],
  "direction": "upstream"
}
```

### Column lineage

When the target uses `model.column` syntax, lineage traces the specific column through upstream or downstream transformations. Each edge is annotated with a transform type (`direct`, `expression`, `aggregation`, `cast`, `star`, `constant`) and a confidence level. See [Column Lineage](/concepts/column-lineage) for a full explanation of transform types, confidence levels, and analysis modes.

```bash
# Where does fact_orders.total_cents come from?
sqb lineage fact_orders.total_cents

# What consumes fact_orders.order_id downstream?
sqb lineage fact_orders.order_id --direction downstream
```

Column lineage supports `upstream` and `downstream` directions (not `both`). The `--mode` flag selects the analysis mode: `rich` (default, full SQL analysis) or `fast` (lightweight, faster on large projects).

#### Tree

```bash
sqb lineage fact_orders.total_cents
```

```
Column trace  fact_orders.total_cents  upstream

  <- stg_payments.amount_cents (expression)
       <- raw__payments.amount_cents (direct)
```

#### List

```bash
sqb lineage fact_orders.total_cents --format list
```

```
Column dependencies

stg_payments.amount_cents -> fact_orders.total_cents  expression
raw__payments.amount_cents -> stg_payments.amount_cents  direct
```

#### JSON

```bash
sqb lineage fact_orders.total_cents --format json
```

```json
{
  "target": {
    "resource_type": "model",
    "resource_name": "fact_orders",
    "column_name": "total_cents"
  },
  "direction": "upstream",
  "metadata": {
    "mode": "rich",
    "max_depth": null,
    "analyzed_models": 5,
    "truncated": false
  },
  "trace": [
    {
      "source": {
        "resource_type": "model",
        "resource_name": "stg_payments",
        "column_name": "amount_cents"
      },
      "target": {
        "resource_type": "model",
        "resource_name": "fact_orders",
        "column_name": "total_cents"
      },
      "transform": "expression",
      "confidence": "high"
    }
  ]
}
```

### Examples

```bash
# Upstream dependencies of a model (default)
sqb lineage fact_orders

# Downstream dependents
sqb lineage fact_orders --direction downstream

# Both directions, limited to 1 hop
sqb lineage fact_orders --direction both --depth 1

# Column lineage: trace a specific column upstream
sqb lineage fact_orders.total_cents

# Column lineage: trace downstream consumers
sqb lineage fact_orders.order_id --direction downstream

# Column lineage with depth limit
sqb lineage fact_orders.total_cents --depth 1

# Lineage for all models in a path
sqb lineage --select path:models/marts

# Lineage between two models (path-between)
sqb lineage --select "stg_orders~daily_activity_rollup"

# Upstream expansion from a model
sqb lineage --select "+fact_orders"

# JSON output for programmatic consumption
sqb lineage fact_orders --format json --direction upstream
```

### Depth limiting

`--depth` controls how many hops from the focus node(s) to include. In selector mode, `--depth` requires name, source, seed, or path-between selectors - it cannot be combined with tag or path selectors or comma-intersection selectors.

```bash
# Only immediate parents
sqb lineage fact_orders --depth 1

# Parents and grandparents
sqb lineage fact_orders --depth 2

# Only direct column dependencies
sqb lineage fact_orders.total_cents --depth 1
```

## dag

Source: `cli/dag.mdx`

Generate the static DAG artifact for Dagster and other integrations.

## sqb dag

Compiles the project and outputs the static DAG artifact. The artifact contains every node (source, seed, model, function), dependency edge, and check (test, audit, scenario) in your project as structured JSON. It is the bridge between SQLBuild and external orchestrators like Dagster.

This artifact describes resource dependencies, not column-level lineage. Use [`sqb lineage`](/cli/lineage) to inspect or export column traces.

### Usage

```bash
sqb --project-dir <path> dag [flags]
```

### Flags

| Flag | Description |
|------|-------------|
| `--json` | Print the full DAG artifact as JSON to stdout |
| `--no-sql-validation` | Skip compile-time SQL syntax validation |
| `--vars` | JSON object of project variable overrides |

Without `--json`, the command prints a summary:

```
DAG ready (24 nodes, 18 edges, 15 checks)
```

### Generating via compile

You can also generate the DAG artifact as part of a compile:

```bash
# Write to default location (target/sqlbuild_dag.json)
sqb compile --dag

# Write to a specific path
sqb compile --dag target/my_dag.json
```

This is useful when you want to compile and generate the DAG in one step. The `SqlBuildProject.prepare()` method in the Dagster integration uses this path.

### Output format

The JSON artifact has this structure:

```json
{
  "version": 1,
  "project_name": "waffle_shop",
  "nodes": [...],
  "edges": [...],
  "checks": [...]
}
```

#### Nodes

Each node represents a source, seed, model, or function:

```json
{
  "id": "model:fact_orders",
  "kind": "model",
  "name": "fact_orders",
  "asset_key": ["dev", "fact_orders"],
  "target": {
    "database": null,
    "schema": "dev",
    "name": "fact_orders",
    "qualified_name": "dev.fact_orders"
  },
  "path": "models/marts/fact_orders.sql",
  "description": "Order fact table with waffle and payment details.",
  "tags": ["marts"],
  "columns": [
    {"name": "order_id", "type": "INTEGER"},
    {"name": "customer_id"}
  ],
  "materialization_type": "table"
}
```

| Field | Description |
|-------|-------------|
| `id` | Unique identifier (`{kind}:{name}`) |
| `kind` | `source`, `seed`, `model`, or `function` |
| `name` | Resource name |
| `asset_key` | Tuple used as the Dagster asset key (typically `[schema, name]` or `[database, schema, name]`) |
| `target` | Warehouse identity (database, schema, name, qualified_name) |
| `path` | Relative file path in the project |
| `description` | Model or source description, if declared |
| `tags` | Model tags |
| `columns` | Column metadata (name, type, nullable, description) |
| `materialization_type` | For models: `view`, `table`, `incremental`, or custom name |
| `language` | For functions: `sql` or `python` |
| `return_kind` | For functions: `scalar` or `table` |
| `arguments` | For functions: argument name and type pairs |

#### Edges

Each edge is a dependency between two nodes:

```json
{
  "from_id": "model:stg_orders",
  "to_id": "model:fact_orders"
}
```

#### Checks

Each check represents a test, audit, or scenario:

```json
{
  "id": "audit:not_null:model:fact_orders:order_id",
  "kind": "audit",
  "name": "not_null",
  "checked_asset_ids": ["model:fact_orders"],
  "path": "audits/generic/not_null.sql",
  "severity": "error",
  "attached_target_name": "fact_orders",
  "attached_column_name": "order_id"
}
```

| Field | Description |
|-------|-------------|
| `id` | Unique check identifier |
| `kind` | `sql_test`, `audit`, or `scenario` |
| `name` | Check name |
| `checked_asset_ids` | Node IDs this check is attached to |
| `path` | Relative file path |
| `severity` | For audits: `error` or `warn` |
| `mode` | For tests: `model`, `macro`, `udf`, or `table_fn` |
| `assertion_names` | For scenarios: names of `__assert__` CTEs |
| `expected_model_names` | For scenarios: names of `__expected__` models |
| `fixture_refs` | For scenarios: names of fixture sources, refs, and seeds |

### Examples

```bash
# Summary output
sqb dag

# Full JSON to stdout
sqb dag --json

# Generate as part of compile
sqb compile --dag

# Generate to a specific path
sqb compile --dag target/sqlbuild_dag.json

# Pipe to jq for inspection
sqb dag --json | jq '.nodes | length'
```

## query

Source: `cli/query.mdx`

Run ad hoc SQL queries against the project database.

## sqb query

Execute ad hoc SQL against the active project connection. Useful for inspecting data, debugging models, or running one-off queries without leaving the SQLBuild CLI.

### Usage

```bash
sqb --project-dir <path> query "SELECT * FROM dev.fact_orders LIMIT 5"
```

Or from a file:

```bash
sqb --project-dir <path> query --file my_query.sql
```

File paths are resolved from the current working directory.

### Flags

| Flag | Description |
|------|-------------|
| `sql` | SQL to execute (positional argument) |
| `--file` | Read SQL from a file instead of the command line |
| `--format` | Output format: `long` (default), `table`, `json`, or `csv` |
| `--limit` | Maximum rows to return (default: 20) |
| `--no-limit` | Disable the row limit |

### Output formats

#### long (default)

Vertical record format, one field per line:

```
-[ RECORD 1 ]---------------------------+
order_id | 1
customer_id | 100
status   | completed

-[ RECORD 2 ]---------------------------+
order_id | 2
customer_id | 200
status   | completed

2 rows
```

#### table

Horizontal table format:

```
order_id | customer_id | status
-------- | ----------- | ---------
1        | 100         | completed
2        | 200         | completed

2 rows
```

#### json

JSON array of objects:

```json
[{"order_id": 1, "customer_id": 100, "status": "completed"}]
```

#### csv

Standard CSV with headers:

```csv
order_id,customer_id,status
1,100,completed
2,200,completed
```

### Examples

```bash
# Quick inspection with default format
sqb query "SELECT * FROM dev.fact_orders"

# Table format with higher limit
sqb query "SELECT * FROM dev.dim_customers" --format table --limit 50

# Export to JSON
sqb query "SELECT * FROM dev.daily_revenue" --format json --no-limit

# Run SQL from a file
sqb query --file debug_query.sql
```

## debug

Source: `cli/debug.mdx`

Validate project configuration and test the warehouse connection.

Checks that your project config is valid, the adapter is resolvable, and the warehouse connection works. Useful for diagnosing setup issues.

### Usage

```bash
sqb debug [flags]
```

### What it checks

The command runs three groups of checks:

**Runtime** - SQLBuild version, Python version, Python path, OS info.

**Configuration** - Finds and validates `sqlbuild_project.toml`, loads `sqlbuild_local.toml` if present, resolves the adapter and active target.

**Connection** - Displays connection settings (secrets are masked), attempts to connect to the warehouse, and runs `SELECT 1` to verify query execution.

### Flags

| Flag | Description |
|------|-------------|
| `--no-connection` | Skip the connection and query tests. Useful for validating config without warehouse access. |
| `--json` | Output results as JSON instead of formatted text. |

### Example

```bash
sqb debug
```

```
SQLBuild Diagnostics

Runtime:
  sqlbuild version: 0.2.1
  python version: 3.14.3
  python path: /home/user/.venv/bin/python3
  os info: Linux-6.6.87

Configuration:
  project file: /home/user/waffle_shop/sqlbuild_project.toml [OK found and valid]
  local config: /home/user/waffle_shop/sqlbuild_local.toml [OK found]
  project: waffle_shop [OK loaded]
  adapter: snowflake [OK found]
  target: dev [OK resolved]

Connection:
  account: FJMQFQV-OJ66172
  authenticator: programmatic_access_token
  database: SQB_DB
  role: role_sqb_test
  schema: TEST
  token: ****
  user: svc_sqb_test
  warehouse: SQB_WH
  connection test: [OK connected]
  query test: [OK SELECT 1]
```

### Exit codes

Returns `0` when all checks pass, `1` when any check fails (e.g. connection refused, invalid config).

## janitor

Source: `cli/janitor.mdx`

Clean up stale warehouse relations.

## sqb janitor

Identifies and removes stale warehouse relations that are no longer part of the project. Requires `janitor.enabled = true` in `sqlbuild_project.toml`.

### Usage

```bash
sqb --project-dir <path> janitor [flags]
```

### Flags

| Flag | Description |
|------|-------------|
| `--auto-approve` | Skip the confirmation prompt and delete immediately |
| `--retention-days` | Override the configured retention period (days) |

### Configuration

Configure janitor behavior in `sqlbuild_project.toml`:

```toml
[janitor]
enabled = true
retention_days = 30
delete_tracked_only = true
exclude_patterns = ["audit_*", "tmp_*"]
```

See [Project Configuration](/concepts/project-configuration) for details on janitor settings.

### Examples

```bash
# Interactive mode (prompts for confirmation)
sqb janitor

# Auto-approve deletion
sqb janitor --auto-approve

# Override retention to 7 days
sqb janitor --retention-days 7
```

### State history pruning

In addition to cleaning up stale relations, the janitor prunes old rows from `_sqlbuild_fingerprints` and `_sqlbuild_source_freshness` tables, retaining only the latest record per identity. This keeps state tables compact without affecting change detection.

### Safety

Janitor prompts for confirmation before deleting. The confirmation requires typing an exact string to prevent accidental deletion. Use `--auto-approve` only in CI or when you're certain.

## clean

Source: `cli/clean.mdx`

Remove compiled artifacts from the target directory.

## sqb clean

Removes the `target/` directory containing compiled artifacts, runtime SQL recordings, and other build outputs.

### Usage

```bash
sqb --project-dir <path> clean
```

No flags. This command has no confirmation prompt since it only removes local build artifacts, not warehouse data.

## dbt

Source: `cli/dbt.mdx`

Coordinate dbt and SQLBuild projects.

## sqb dbt

Orchestrate dbt and SQLBuild together. Each subcommand runs dbt first, then SQLBuild, with selection logic across both project graphs. dbt remains responsible for dbt-owned models; SQLBuild validates and executes SQLBuild-owned models downstream. See [Using SQLBuild with dbt](/concepts/dbt-compatibility/overview) for scope and selection behavior.

### sqb dbt plan

Preview combined dbt and SQLBuild work without executing.

```bash
sqb dbt plan [--select <selector>...] [--exclude <selector>...] [--json] [--verbose]
```

Shows which dbt models will run, which SQLBuild models will run, and the dbt/SQLBuild commands that would be executed.

### sqb dbt run

Run dbt models first, then SQLBuild models.

```bash
sqb dbt run [--select <selector>...] [--exclude <selector>...]
```

### sqb dbt build

Build dbt models first (including dbt tests), then SQLBuild models with audits.

```bash
sqb dbt build [--select <selector>...] [--exclude <selector>...]
```

### sqb dbt debug

Run dbt diagnostics followed by SQLBuild diagnostics.

```bash
sqb dbt debug [--no-connection]
```

### Selectors

All `sqb dbt` commands accept `--select` and `--exclude`. Selectors work across both dbt and SQLBuild:

```bash
# SQLBuild model with dbt dependencies
sqb dbt build --select downstream_orders

# Full upstream chain including dbt
sqb dbt build --select +downstream_orders

# Downstream of modified dbt models
sqb dbt build --select state:modified+

# SQLBuild models by tag
sqb dbt build --select tag:nightly

# SQLBuild models by path
sqb dbt build --select path:models/marts

# Exclude by tag
sqb dbt build --select fact_orders+ --exclude tag:nightly
```

See [Selection](/concepts/dbt-compatibility/selection) for full details on how selectors route work between dbt and SQLBuild.

### Configuration

Configure the dbt project location in `sqlbuild_project.toml`:

```toml
[dbt]
project_dir = "../dbt_project"
profiles_dir = "../profiles"
target_path = "../dbt_project/target"
```

See [Project Configuration](/concepts/project-configuration#dbt) for all fields.

## state

Source: `cli/state.mdx`

Manage the virtual mode state store.

## sqb state

Manages the virtual mode state store lifecycle, locks, and checkpoints. Requires `virtual_environments = true`.

### Usage

```bash
sqb state <subcommand> [flags]
```

### Subcommands

#### init

Create state tables in the configured schema.

```bash
sqb state init
```

#### migrate

Back up the current state schema and re-initialize state tables. Creates a backup schema (e.g. `sqlbuild_state__backup_<id>`) before re-initializing.

```bash
sqb state migrate
```

#### rollback

Restore state from a backup.

```bash
# Restore from the latest backup
sqb state rollback

# Restore from a specific backup
sqb state rollback --backup-id <id>
```

#### reset

Drop all state tables. Requires `allow_reset = true` in the target state config and `--auto-approve` on the command line.

```bash
sqb state reset --auto-approve
```

#### adopt

Convert existing stateless warehouse relations into versioned physical relations with VDE views. Interactive only - requires typed confirmation.

```bash
sqb state adopt [--allow-copy]
```

| Flag | Description |
|------|-------------|
| `--allow-copy` | Allow CTAS copy fallback when native rename is not available |

See [Adopt and Detach](/concepts/virtual-environments/adopt-detach) for details.

#### detach

Collapse a VDE back into stateless warehouse relations. Interactive only - requires typed confirmation. The VDE must be finalized.

```bash
sqb state detach [--allow-copy]
```

| Flag | Description |
|------|-------------|
| `--allow-copy` | Allow CTAS copy fallback when native rename is not available |

#### locks

List active locks in the state store.

```bash
sqb state locks
```

#### locks clear

Clear a stuck lock.

```bash
sqb state locks clear <lock_key> --force
```

Only clear locks when you are certain the holding operation is no longer running.

#### checkpoints list

List finalized checkpoints for a VDE.

```bash
sqb state checkpoints list [--virtual-env <name>]
```

#### checkpoints show

Show the model refs stored in a checkpoint.

```bash
sqb state checkpoints show <checkpoint_id> [--virtual-env <name>]
```

#### checkpoints diff

Diff current VDE refs against a checkpoint.

```bash
sqb state checkpoints diff <checkpoint_id> [--virtual-env <name>]
```

## promote

Source: `cli/promote.mdx`

Promote VDE refs from one virtual environment to another.

## sqb promote

Promotes model version refs from a source VDE to a target VDE. No models are rebuilt - promotion swaps pointers and refreshes logical views. Virtual mode only.

### Usage

```bash
sqb promote --from <source_vde> --to <target_vde> [flags]
```

### Flags

| Flag | Description |
|------|-------------|
| `--from` | Source VDE name (required) |
| `--to` | Target VDE name (required) |
| `--select`, `-s` | Select specific models to promote |
| `--exclude` | Exclude specific models |
| `--allow-partial-promotion` | Accept a working target VDE when partial promotion leaves downstream stale |
| `--include-stale-upstreams` | Add required stale upstream refs to the promotion scope |
| `--verbose`, `-v` | Show uncapped model sets |
| `--var` | Set project variables |

### Examples

```bash
# Promote all models from pr_123 to dev
sqb promote --from pr_123 --to dev

# Promote specific models
sqb promote --from pr_123 --to dev --select fact_orders

# Partial promotion with working target accepted
sqb promote --from pr_123 --to dev --select fact_orders --allow-partial-promotion

# Include stale upstreams for coherent partial promotion
sqb promote --from pr_123 --to dev --select fact_orders --include-stale-upstreams
```

See [Promotion](/concepts/virtual-environments/promotion) for details on promotion behavior, source requirements, and guards.

## rollback

Source: `cli/rollback.mdx`

Roll back a VDE to a prior finalized checkpoint.

## sqb rollback

Restores a virtual environment to a prior finalized checkpoint by rebinding its refs and refreshing logical views. Virtual mode only.

### Usage

```bash
sqb rollback [flags]
```

### Flags

| Flag | Description |
|------|-------------|
| `--virtual-env` | Target VDE name (defaults to active target name) |
| `--checkpoint-id` | Restore a specific checkpoint instead of the previous one |
| `--select`, `-s` | Roll back specific models only |
| `--exclude` | Exclude specific models |
| `--allow-partial-rollback` | Accept a working VDE when partial rollback leaves downstream stale |
| `--include-stale-upstreams` | Add required upstream refs from the checkpoint |
| `--verbose`, `-v` | Show uncapped model sets |
| `--var` | Set project variables |

### Examples

```bash
# Roll back to the previous finalized checkpoint
sqb rollback

# Roll back a specific VDE
sqb rollback --virtual-env pr_123

# Roll back to a specific checkpoint
sqb rollback --checkpoint-id <id>

# Partial rollback
sqb rollback --select fact_orders --allow-partial-rollback
```

See [Rollback](/concepts/virtual-environments/rollback) for details on checkpoints, rollback behavior, and guards.

## reconcile

Source: `cli/reconcile.mdx`

Diagnose and repair drift between virtual state and warehouse.

## sqb reconcile

Detects and repairs inconsistencies between the virtual state store and the warehouse. Virtual mode only.

### Usage

```bash
sqb reconcile [--virtual-env <name>] [--model <name>]
sqb reconcile repair-view --virtual-env <name> --model <name>
sqb reconcile attach --virtual-env <name> --model <name> --physical-relation <relation>
```

### Subcommands

#### (default)

Run a diagnostic report without changing anything:

```bash
sqb reconcile --virtual-env dev
```

#### repair-view

Recreate a logical VDE view from trusted state refs:

```bash
sqb reconcile repair-view --virtual-env dev --model fact_orders
```

No confirmation needed. Idempotent (`CREATE OR REPLACE VIEW`).

#### attach

Rebind a VDE model ref to a different tracked physical relation:

```bash
sqb reconcile attach --virtual-env dev --model fact_orders \
  --physical-relation dev__sqb_physical.fact_orders__v_8f3a9c12
```

Requires confirmation by default.

### Examples

```bash
# Diagnose issues
sqb reconcile --virtual-env dev

# Fix a missing view
sqb reconcile repair-view --virtual-env dev --model fact_orders

# Rebind a model to a different physical version
sqb reconcile attach --virtual-env dev --model fact_orders \
  --physical-relation dev__sqb_physical.fact_orders__v_71d0e4ab
```

See [Reconcile](/concepts/virtual-environments/reconcile) for details on guards and when to use each subcommand.

## Enums and Constants Have Moved

Source: `concepts/enums-and-constants.mdx`

Find the new focused guides for enums, constants, collections, contracts, and private values.

Enums and constants now have separate guides so each feature is easier to find and learn. This page
remains available for existing links and bookmarks but is not part of the main navigation.

    Define fixed string or integer domains and reference validated members.
    Define reusable scalar values and reference them safely from SQL.
    Work with lists, sets, objects, value lists, and native arrays.
    Keep enums and constants inside one model.

### Public declarations

See [Enums](/concepts/enums) and [Constants](/concepts/constants) for project-wide declarations.

### Constant values

See [Constants](/concepts/constants#scalar-values) for scalars and
[Collections and Rendering](/concepts/constants/collections-and-rendering) for collections.

### References and rendering

See [Collections and Rendering](/concepts/constants/collections-and-rendering).

### Adapter matrix

See the [native-array rendering matrix](/concepts/constants/collections-and-rendering#native-array-rendering).

### Rendering configuration

See [Project default](/concepts/constants/collections-and-rendering#project-default).

### Model-local declarations

See [Model-Private Values](/concepts/model-private-values).

### Model-private declarations

See [Model-Private Values](/concepts/model-private-values).

### Enum validation

See [Enum validation rules](/concepts/enums#validation-rules).

### Enum-typed contracts

See [Enum Model Contracts](/concepts/enums/model-contracts).
