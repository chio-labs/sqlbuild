---
name: sqlbuild
description: Use when working with SQLBuild syntax, project structure, configuration, testing, adapters, CLI behavior, SQLBuild docs, or SQLBuild-related code.
---

<!-- generated-by: sqlbuild skills update -->

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
- `concepts/enums-and-constants`
- `concepts/interpolation`
- `concepts/macros`
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

## Introduction

Source: `index.mdx`

Verify early, test properly, and deploy reversibly. SQL pipelines with the rigor of real software - on your existing dbt project, free and open source.

**Valid isn't the same as correct.** Your SQL compiles, runs, and returns rows - none of that means the number is right, and a silently-wrong number a stakeholder already trusted is the bug that actually hurts.

SQLBuild brings software-engineering rigor to SQL pipelines: **verify early, test properly, deploy reversibly.** Catch errors before the warehouse runs them and test your logic locally - with change-aware builds and reversible deploys there when you need them, not forced on you on day one. It works on a standalone SQL project or [points at your existing dbt project](/concepts/dbt-compatibility/overview) with no migration - free and open source.

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

See [Testing](/concepts/scenarios) for unit tests, scenarios, and local replay.

### Verify early

Before any model runs, SQLBuild does static analysis of your project - offline, no warehouse connection needed.

- **Catch errors at compile.** SQL syntax, type inference, contract checks, and column lineage all run before execution. A bad reference or a type mismatch fails at compile, with an error that points at the line - not halfway through a warehouse run.
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

State is plain append-only rows in your own warehouse (`_sqlbuild_fingerprints`, `_sqlbuild_source_freshness`, `_sqlbuild_node_results`) - no external state database, no manifest files, no state machine that can corrupt. Point SQLBuild at an [existing dbt project](/concepts/dbt-compatibility/overview) and the same opt-in change detection prunes unchanged dbt models from the run - nothing metered, no account, nothing to log into.

### Deploy reversibly (opt-in)

By default, SQLBuild runs in standard mode with state as append-only rows in your warehouse. When you want more, [virtual environments](/concepts/virtual-environments) add a reversibility layer on top:

- **Instant branching, promotion, and rollback** as low-copy pointer operations.
- **Partial promotion.** Promote the models that are ready without re-running everything downstream of them - you don't have to rebuild the whole closure to ship one fix.
- **Checkpoints and reconciliation** so a bad change is something you undo, not an incident.

Virtual environments are opt-in, not a tax you pay upfront - standard mode stays the default, so the floor stays low and you reach for them only when a workflow needs them.

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
  description: "Daily revenue includes only successful payments",
  tags: ["revenue"]
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
- **Deferred references:** Compile and plan against a production target with `--defer-to` while building in dev.
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
    Full reference for every SQLBuild command.
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
| Macros as test helpers | Tests are SQL - macros work as reusable fixture generators | No (YAML stubs) | No |
| E2E scenario tests | Fixture worlds with real graph execution | No | No |
| Local E2E replay | Capture from warehouse, replay in DuckDB | No | No |
| Macro / UDF / table function tests | `TEST(mode: macro/udf/table_fn)` | No | No |
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
| SQL transpilation | For local E2E replay into DuckDB | No | For cross-dialect model execution |
| Python macros | `@macro()` syntax | No (Jinja only) | SQLMesh macro syntax |
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
| Lifecycle hooks | Typed `sql()`/`python()` hooks with compile-time validation and `HookContext` | Jinja pre/post hooks | Python pre/post hooks |

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
| dbt compatibility | Run alongside dbt - reads manifest, unified selection, SQLBuild models downstream, no migration | N/A | Jinja compatibility layer plus own macro system |

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
| AI agent skills | `sqb skills update` | No | No |

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

Run your existing dbt project through SQLBuild. No SQLBuild models and no migration.

Point SQLBuild at your existing dbt project and run your dbt selections through it, layering SQLBuild models, tests, and audits downstream when you want them. No migration, no edits to your dbt files.

SQLBuild reads your dbt manifest and drives the `dbt` CLI as a subprocess. It never edits, patches, or moves files in your dbt project, and it does not reimplement Jinja, profiles, or dbt's selection language. Your dbt project runs exactly as it does today.

### Start with your existing dbt project

From inside your dbt project, run a `sqb dbt` command. Selection works exactly like dbt: scope to whatever you would normally build with `--select`, or omit it to plan the whole project.

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

[targets.dev]
schema = "analytics"

[targets.dev.connection]
source = "dbt_profile"
profile = "analytics"
target = "dev"
```

`source = "dbt_profile"` tells SQLBuild to connect using your dbt profile, so it talks to the same warehouse dbt does.

`sqb dbt build --select path:models/marts` compiles the project, resolves the selection, runs the selected dbt models, then runs any SQLBuild models you have added against the dbt outputs.

### How it works

1. SQLBuild runs `dbt compile` to produce a `manifest.json` with model metadata
2. SQLBuild reads the manifest to understand dbt model names and their qualified warehouse tables
3. SQLBuild resolves your `--select`/`--exclude` against dbt by running `dbt ls`, so dbt-native selectors like `state:modified` and `package:` are evaluated by dbt itself, not reimplemented
4. `sqb dbt plan/run/build` orchestrates the run: dbt builds the full selection, exactly like dbt
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
| `--full-refresh` | dbt **and** SQLBuild | Forces a full rebuild of selected models on both sides. |
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

Running your dbt project through SQLBuild needs no SQLBuild models. This page is the optional next step: you can write SQLBuild models, tests, audits, and scenarios downstream of your dbt project without leaving it.

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

[connection]
database = "waffle_shop_control.duckdb"

[settings]
default_audit_severity = "warn"

[defaults]
materialized = "table"

[targets.prod]
schema = "prod"

[targets.dev]
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

#### Connection

The `connection` block is passed directly to the adapter. For DuckDB:

```toml
[connection]
database = "my_project.duckdb"
```

Targets can override the connection:

```toml
[targets.prod]
schema = "prod"

[targets.prod.connection]
database = "prod.duckdb"

[targets.dev]
schema = "dev"

[targets.dev.connection]
database = "dev.duckdb"
```

### Targets

A target is a named build context - the schema, database, or connection you build against (for example `dev` and `prod`). Targets let you build to different places from the same project. Each target can override:

| Field | Description |
|-------|-------------|
| `schema` | Schema for all models in this target |
| `loader_schema` | Default write schema for managed source loaders; falls back to `schema` |
| `database` | Database for all models in this target |
| `connection` | Override the base connection config |
| `vars` | Target-specific project variables |
| `defer_sources_to` | Target name to read managed source data from (see [Loaders](/concepts/python-nodes/loaders#source-deferral)) |
| `clone` | Clone policy (see below) |

```toml
[targets.prod]
schema = "analytics_prod"
loader_schema = "raw_prod"
defer_sources_to = "prod"

[targets.dev]
schema = "analytics_dev"
loader_schema = "raw_dev"
defer_sources_to = "prod"

[targets.staging]
schema = "staging"

[targets.staging.connection]
database = "staging.duckdb"
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
schema = "dev_alice"
loader_schema = "raw_alice"
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
concurrency = 1
auto_load_sources = true
table_promotion_mode = "staged"
default_audit_severity = "warn"
default_audit_run_scope = "final"
```

| Field | Default | Description |
|-------|---------|-------------|
| `sql_analysis` | `true` | Enable SQL validation and static analysis at compile time |
| `changes_only` | `false` | Enable [change-aware pruning](/concepts/planning#changes-only-mode) for `plan` and `build` without passing `--changes-only` each run. Requires `virtual_environments = true`; rejected in standard mode. Can also be set per target under `[targets.<name>]`. The CLI flag takes precedence, then the selected target, then local settings, then this project setting. |
| `virtual_environments` | `false` | Enable [virtual environments](/concepts/virtual-environments) (versioned model outputs, promotion, rollback, state management). When `false`, the project runs in standard mode. |
| `query_change_tracking` | `true` | Track query fingerprints for change detection |
| `sql_validation` | `true` | Validate SQL syntax during compilation |
| `concurrency` | `1` | Maximum parallel model execution (currently serial only) |
| `auto_load_sources` | `true` | Automatically run source loaders before building dependent models during `sqb build`. See [Loaders](/concepts/python-nodes/loaders). |
| `table_promotion_mode` | adapter default | `staged` (CTAS to staging, audit, then promote) or `direct` (CTAS directly to target) |
| `default_audit_severity` | `warn` | Default severity for audits: `warn` or `error` |
| `default_audit_run_scope` | `final` | Default run scope for audits: `final` or `delta_and_final` |

#### Table promotion mode

- **`staged`** (default for most adapters): Materializes into a staging table, runs audits, then swaps into the target. If audits fail, the production table is untouched.
- **`direct`**: Creates the table directly at the target location. Audits run after materialization. Simpler but no pre-promotion safety net.

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
targets = ["opencode", "claude"]
```

| Field | Default | Description |
|-------|---------|-------------|
| `targets` | all targets | Which agent targets to install skill files for: `opencode`, `claude`, `agents` |

See [skills CLI reference](/cli/skills) for usage details.

### sqlbuild_local.toml

Local developer overrides. This optional file is loaded automatically and should be
gitignored. Only put values that differ from the shared project configuration here.

```toml
target = "dev"

[targets.dev]
schema = "dev_alice"
loader_schema = "raw_alice"

[targets.dev.connection]
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
| `connection` | Override connection config (merged on top of project + target connection) |
| `settings` | Override global settings (only explicitly set fields take effect) |
| `vars` | Developer-specific variable overrides (merged on top of project + target vars) |

Target blocks support the same local overrides, including `schema`, `loader_schema`,
`connection`, `vars`, source deferral, and clone policy fields. Unspecified values
continue to come from `sqlbuild_project.toml`.

This replaces the common dbt pattern of switching profiles or setting environment variables
to change targets. Each developer sets their target, connection, and preferences once in
`sqlbuild_local.toml` and it persists across sessions.

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

[connection]
database = "my_project.duckdb"
```

| Field | Description |
|-------|-------------|
| `database` | Path to the DuckDB database file. Use `:memory:` for in-memory databases. |
| `extensions` | List of DuckDB extensions to install and load on connect. |
| `settings` | Key-value pairs passed as `SET` statements on connect. |
| `attach` | List of additional databases to attach. |

### Extensions and settings

```toml
[connection]
database = "my_project.duckdb"
extensions = ["httpfs", "parquet"]

[connection.settings]
memory_limit = "4GB"
```

### Attaching additional databases

```toml
[connection]
database = "my_project.duckdb"

[[connection.attach]]
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

[connection]
database = "my_database"
token = "your_motherduck_token"
```

| Field | Description |
|-------|-------------|
| `database` | MotherDuck database name. Automatically prefixed with `md:` if not already present. Defaults to `md:` (your default MotherDuck database). |
| `token` | MotherDuck access token. Can also be set via environment variable. |

### Authentication

MotherDuck requires an access token. Generate one from the MotherDuck UI and pass it via the connection config or an environment variable:

```toml
[connection]
database = "my_database"
token = "${ENV:MOTHERDUCK_TOKEN}"
```

### Per-target connections

Use targets to separate production and development databases on MotherDuck:

```toml
adapter = "motherduck"

[connection]
token = "${ENV:MOTHERDUCK_TOKEN}"

[targets.prod]
schema = "prod"

[targets.prod.connection]
database = "prod_db"

[targets.dev]
schema = "dev"

[targets.dev.connection]
database = "dev_db"
```

### Local development with DuckDB

Use `sqlbuild_local.toml` to override the adapter for local development against a plain DuckDB file:

```toml
adapter = "duckdb"

[connection]
database = "local_dev.duckdb"
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

[connection]
account = "my_org-my_account"
user = "my_user"
password = "my_password"
role = "TRANSFORM_ROLE"
warehouse = "TRANSFORM_WH"
database = "ANALYTICS"
schema = "RAW"
```

All fields in `connection` are passed directly to `snowflake.connector.connect()`. See the [Snowflake Connector documentation](https://docs.snowflake.com/en/developer-guide/python-connector/python-connector-connect) for all available options, including key-pair authentication, OAuth, and SSO.

### Session initialization

On connect, SQLBuild runs `USE ROLE`, `USE WAREHOUSE`, `USE DATABASE`, and `USE SCHEMA` statements based on the connection config. These ensure the session context is set correctly regardless of the user's default settings.

### Per-target connections

Use targets to connect to different Snowflake databases or warehouses:

```toml
adapter = "snowflake"

[connection]
account = "my_org-my_account"
user = "my_user"
password = "my_password"

[targets.prod]
schema = "prod"

[targets.prod.connection]
role = "PROD_ROLE"
warehouse = "PROD_WH"
database = "PROD_DB"

[targets.dev]
schema = "dev"

[targets.dev.connection]
role = "DEV_ROLE"
warehouse = "DEV_WH"
database = "DEV_DB"
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

[connection]
project = "my-gcp-project"
location = "europe-west2"
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
[connection]
project = "my-gcp-project"
credentials_path = "/path/to/service-account.json"
```

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

[connection]
server_hostname = "my-workspace.cloud.databricks.com"
http_path = "/sql/1.0/warehouses/abc123"
token = "dapi_my_access_token"
catalog = "my_catalog"
schema = "my_schema"
```

| Field | Description |
|-------|-------------|
| `server_hostname` | Databricks workspace hostname (required) |
| `http_path` | SQL warehouse or cluster HTTP path (required) |
| `token` | Personal access token (required) |
| `catalog` | Unity Catalog name (required) |
| `schema` | Default schema (optional) |

### Session initialization

On connect, SQLBuild runs `USE CATALOG` and `USE SCHEMA` statements to set the session context.

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

[connection]
host = "localhost"
port = 5432
user = "my_user"
password = "my_password"
dbname = "my_database"
```

| Field | Description |
|-------|-------------|
| `host` | PostgreSQL server hostname (default: `localhost`) |
| `port` | PostgreSQL server port (default: `5432`) |
| `user` | Database user |
| `password` | Database password |
| `dbname` | Database name |

All fields in `connection` are passed to `psycopg.connect()`. See the [psycopg documentation](https://www.psycopg.org/psycopg3/docs/api/connections.html) for all available options.

### Per-target connections

```toml
adapter = "postgres"

[connection]
host = "localhost"
user = "my_user"
password = "${ENV:PG_PASSWORD}"

[targets.prod]
schema = "prod"

[targets.prod.connection]
host = "prod-db.example.com"
dbname = "analytics"

[targets.dev]
schema = "dev"

[targets.dev.connection]
dbname = "analytics_dev"
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

[connection]
host = "localhost"
port = 1433
user = "sa"
password = "my_password"
database = "my_database"
```

| Field | Description |
|-------|-------------|
| `host` | SQL Server hostname (default: `localhost`). Also accepts `server` as an alias. |
| `port` | SQL Server port (default: `1433`) |
| `user` | Database user (default: `sa`). Also accepts `username` as an alias. |
| `password` | Database password |
| `database` | Database name (default: `master`). Also accepts `dbname` as an alias. |

All fields in `connection` are passed to `pymssql.connect()`. See the [pymssql documentation](https://pymssql.readthedocs.io/en/stable/ref/pymssql.html) for all available options.

SQL Server supports schema-only, full-row, and bounded `sqb diff` comparisons.

### Per-target connections

```toml
adapter = "sqlserver"

[connection]
host = "localhost"
user = "sa"
password = "${ENV:MSSQL_PASSWORD}"

[targets.prod]
schema = "prod"

[targets.prod.connection]
host = "prod-sql.example.com"
database = "analytics"

[targets.dev]
schema = "dev"

[targets.dev.connection]
database = "analytics_dev"
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

Type enforcement is implicit for sources, the same as for models. If any column declares a `type`, SQLBuild automatically casts that column and uses declared types for schema-change detection:

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

## Models

Source: `concepts/models.mdx`

SQL model definitions, the MODEL() block, materialization types, and how the DAG is built.

A model is a SQL file that defines one transformation step. Each model produces one table or view in the warehouse.

### MODEL() header

Every model file starts with a `MODEL()` block that declares its materialization, configuration, and schema metadata:

```sql
MODEL (
  materialized table,
  tags [marts],
  description "Order fact table with waffle and payment details.",
  columns (
    order_id (audits [not_null]),
  ),
);

SELECT
  o.order_id,
  o.customer_id,
  w.waffle_name,
  w.price_cents * o.quantity AS line_total_cents
FROM __ref("stg_orders") o
LEFT JOIN __seed("waffle_types") w ON o.waffle_type_id = w.waffle_type_id
```

### Materialization types

#### view

Creates a database view. Rebuilt on every run.

```sql
MODEL (
  materialized view,
  tags [staging],
);

SELECT id AS order_id, customer_id, status
FROM __source("raw__orders")
```

#### table

Creates a table via `CREATE TABLE AS`. SQLBuild materializes into a staging table first, runs audits, then promotes to the target. Fully rebuilt each time.

```sql
MODEL (
  materialized table,
  tags [marts],
);

SELECT customer_id, COUNT(*) AS total_orders
FROM __ref("stg_orders")
GROUP BY customer_id
```

#### incremental

Inserts or updates into an existing table using a cursor-based strategy. See [Incremental](/concepts/incremental) for full configuration.

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

#### snapshot

Maintains historical row versions with SCD Type 2 semantics. Supports timestamp-based and value-check-based change detection, historical source inputs, hard delete invalidation, and configurable full-refresh safety policies.

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

See [Snapshots](/concepts/snapshots) for full configuration, historical input modes, and querying patterns.

#### custom

User-defined Python materialization function. Custom materializations get full access to the framework including adapter, schema change signals, query change detection, and audit hooks.

```sql
MODEL (
  materialized partition_tracked,
  tags [marts],
  placeholders (
    partition_start "'2026-04-01'",
    partition_end "'2026-04-05'",
  ),
  config (
    tracking_table partition_state,
    partition_column order_date,
    date_range_start 2026-04-01,
    date_range_end 2026-04-05,
  ),
  description "Partition-tracked daily order summary using custom materialization.",
  columns (
    order_date (audits [not_null]),
  ),
  audits [
    expression_is_true (
      name "waffles ordered is positive",
      expression "waffles_ordered > 0",
    ),
  ],
);

SELECT
  CAST(o.ordered_at AS DATE) AS order_date,
  COUNT(DISTINCT o.order_id) AS order_count,
  SUM(o.quantity) AS waffles_ordered,
  COUNT(DISTINCT o.customer_id) AS unique_customers
FROM __ref("stg_orders") o
WHERE CAST(o.ordered_at AS DATE) >= CAST(@@@partition_start AS DATE)
  AND CAST(o.ordered_at AS DATE) < CAST(@@@partition_end AS DATE)
GROUP BY CAST(o.ordered_at AS DATE)
```

Custom materializations use `@@@placeholder` syntax for values substituted at runtime. These deferred placeholders are preserved through compilation and resolved by the materialization at execution time. The `config` block passes arbitrary key-value pairs to the Python `materialize()` function via `ctx.config`.

### References

Models use typed reference calls that SQLBuild resolves to qualified warehouse relation names during compilation:

| Reference | Syntax | Resolves to |
|-----------|--------|-------------|
| Model | `__ref("name")` | Another model |
| Seed | `__seed("name")` | A seed CSV table |
| Source | `__source("name")` | An external source |
| Scalar UDF | `__udf("name")` | A user-defined function |

```sql
SELECT
  o.order_id,
  o.customer_id,
  w.waffle_name,
  w.price_cents * o.quantity AS line_total_cents,
  __udf("udf__is_completed_order")(o.status) AS is_completed
FROM __ref("stg_orders") o
LEFT JOIN __seed("waffle_types") w ON o.waffle_type_id = w.waffle_type_id
```

Seeds use `__seed()`, not `__ref()`. Using `__ref()` with a seed name raises a compile error with a helpful message pointing you to `__seed()`.

See [Functions](/concepts/functions) for UDF and table function details.

### DAG ordering

SQLBuild automatically discovers the dependency graph from reference calls, then executes models in topological order. Upstream models are always built before their downstream dependents.

### Schema declarations

Model metadata - description, columns, audits, and type information - lives directly in the `MODEL()` header. There is no separate `schema.yml` for models.

```sql
MODEL (
  materialized view,
  tags [staging],
  description "Cleaned order records.",
  columns (
    order_id (audits [not_null, unique]),
    customer_id (audits [not_null]),
    status (
      audits [
        accepted_values (values ["placed", "preparing", "ready", "completed", "cancelled"]),
      ],
    ),
  ),
);

SELECT
  id AS order_id,
  customer_id,
  status
FROM __source("raw__orders")
```

#### Column-level audits

Attach audits to individual columns inside the `columns` block. Simple audits like `not_null` and `unique` are listed by name. Parameterized audits like `accepted_values` pass arguments inline:

```sql
columns (
  order_id (audits [not_null, unique]),
  status (
    audits [
      accepted_values (values ["placed", "preparing", "completed", "cancelled"]),
    ],
  ),
),
```

#### Model-level audits

Attach audits to the model itself for multi-column or expression-based checks:

```sql
MODEL (
  materialized table,
  audits [
    expression_is_true (
      name "revenue is non-negative",
      expression "total_revenue_cents >= 0",
    ),
  ],
);
```

#### Type enforcement

Type enforcement is implicit. If any column in the `MODEL()` header declares a `type`, type enforcement is automatically enabled for that model:

```sql
MODEL (
  materialized table,
  columns (
    order_id (type INTEGER, audits [not_null]),
    amount_cents (type INTEGER),
  ),
);
```

When enabled, SQLBuild casts columns to declared types and uses them for schema-change detection. There is no need to set `type_enforcement: true` explicitly.

#### Contracts

Contracts enforce that a model's output matches its declared column schema exactly - column names, column count, and column types. When `contract enforced` is set, the declared columns become the authoritative output contract.

```sql
MODEL (
  materialized table,
  contract enforced,
  columns (
    order_id (type INTEGER, audits [not_null]),
    customer_id (type INTEGER, audits [not_null]),
    amount_cents (type INTEGER),
    status (type VARCHAR),
  ),
);
```

Contract enforcement happens at two levels:

**Compile time** - config fields that reference columns (`unique_key`, `cursor`, `updated_at`, `check_columns`) are validated against the declared column names. If a referenced column is not in the contract, compilation fails.

**Runtime** - after materialization into the staging table, SQLBuild inspects the actual output columns and validates them against the contract before promotion:

- Missing declared columns fail with code `K010`
- Extra undeclared columns fail with code `K011`
- Type mismatches (e.g. `VARCHAR` where `INTEGER` was declared) fail with code `K013`

If any validation fails, the production table is untouched. Types are compared using adapter-aware normalization, so equivalent types across dialects are handled correctly.

Contract values:

| Value | Behavior |
|-------|----------|
| `enforced` | Declared columns are the complete, authoritative output schema |
| `none` | No contract enforcement (default) |

Contracts interact with schema change policies. For snapshot models, `snapshot_schema_change append_new_columns` is incompatible with `contract enforced` because appending columns would violate the contract.

Columns may also use a declared enum as their type:

```sql
MODEL (
  contract enforced,
  columns (
    market_type (type market_type),
  ),
);
```

SQLBuild resolves the enum to its physical string or integer type and adds accepted-values validation for its members. See [Enums and Constants](/concepts/enums-and-constants).

#### Audit run scope

Audits on incremental models can specify `run_scope` to control when they execute:

```sql
MODEL (
  materialized incremental,
  incremental_strategy delete_insert,
  cursor activity_hour,
  cursor_type timestamp,
  cursor_grain hour,
  columns (
    activity_hour (audits [not_null (run_scope delta_and_final)]),
  ),
  audits [
    expression_is_true (
      name "orders placed is non-negative",
      expression "orders_placed >= 0",
      run_scope delta_and_final,
    ),
  ],
);
```

`delta_and_final` runs the audit against each delta batch before DML and again against the target after all batches complete. See [Audits](/concepts/audits) for details.

### Hooks

Pre-hooks and post-hooks run before and after materialization. Each entry is either a `sql("...")` hook that executes SQL, or a `python("hook_name")` hook that calls a Python function from the `hooks/` directory.

#### SQL hooks

```sql
MODEL (
  materialized table,
  post_hooks [sql('GRANT SELECT ON @@CTX:destination.qualified TO analyst_role')],
);
```

SQL hooks support macro expansion (`@macro()`), project variables (`@@name`), environment variables (`@@ENV:NAME`), and context variables (`@@CTX:`). SQL is validated at compile time when SQL analysis is enabled.

Available context variables in hooks:

| Variable | Value |
|----------|-------|
| `@@CTX:destination.qualified` | Fully qualified destination relation name |
| `@@CTX:destination.schema` | Destination schema |
| `@@CTX:destination.table` | Destination relation name |
| `@@CTX:model.name` | Model name |
| `@@CTX:run.target` | Active target name |
| `@@CTX:run.id` | Current run ID |

#### Python hooks

Python hooks call `@hook`-decorated functions discovered from the `hooks/` directory:

```python
# hooks/permissions.py
from sqlbuild.hooks import hook

@hook
def grant_analyst(ctx):
    ctx.execute_sql(f"GRANT SELECT ON {ctx.destination.qualified} TO analyst_role")
```

Reference a Python hook in the MODEL() header by name, with optional keyword arguments:

```sql
MODEL (
  materialized table,
  post_hooks [python("grant_analyst")],
);
```

```sql
MODEL (
  materialized table,
  post_hooks [python("grant_analyst", role: "reader_role")],
);
```

You can mix SQL and Python hooks in the same list:

```sql
MODEL (
  materialized table,
  pre_hooks [sql('SET search_path TO analytics')],
  post_hooks [
    python("grant_analyst"),
    sql('ANALYZE @@CTX:destination.qualified'),
  ],
);
```

#### Hook context

Python hooks receive a `HookContext` as their first parameter (named `ctx`, `context`, or `hook_context`):

| Field | Description |
|-------|-------------|
| `ctx.model_name` | Name of the model being built |
| `ctx.phase` | `pre_hooks` or `post_hooks` |
| `ctx.hook_name` | Name of the hook being invoked |
| `ctx.run_id` | Current run ID |
| `ctx.target` | Active target name |
| `ctx.vars` | Project variables |
| `ctx.destination.qualified` | Fully qualified destination relation name |
| `ctx.destination.schema` | Destination schema |
| `ctx.destination.name` | Destination relation name |
| `ctx.destination.database` | Destination database |
| `ctx.adapter` | Adapter instance |
| `ctx.connection` | Live connection |
| `ctx.execute_sql(sql)` | Execute SQL on the connection |
| `ctx.query(sql)` | Execute SQL and return rows |
| `ctx.log(message)` | Log to the run output |
| `ctx.skip(reason, mode=...)` | Skip the model's materialization. `mode` accepts `"soft"` (default) or `"hard"` (blocks downstream models). |
| `ctx.providers` | Access discovered [providers](/concepts/python-nodes/providers) by name |

Pre-hooks can return `ctx.skip(...)` to skip the model's materialization entirely. A soft skip skips only this model; a hard skip also blocks downstream models. Providers can also be injected directly as hook function parameters by name. See [Providers](/concepts/python-nodes/providers).

#### Hook decorator

The `@hook` decorator accepts optional metadata:

```python
from sqlbuild.hooks import hook

@hook
def grant_analyst(ctx):
    """Grant analyst role on the destination table."""
    ctx.execute_sql(f"GRANT SELECT ON {ctx.destination.qualified} TO analyst_role")

@hook(name="custom_name", description="Custom hook with explicit name")
def my_hook(ctx, role="analyst_role"):
    ctx.execute_sql(f"GRANT SELECT ON {ctx.destination.qualified} TO {role}")
```

| Argument | Description |
|----------|-------------|
| `name` | Override the hook name (defaults to the function name) |
| `description` | Human-readable description (defaults to the function docstring) |

#### Discovery rules

- Hook functions are discovered from `.py` files under `hooks/` recursively
- Files named `__init__.py` or starting with `_` are skipped
- Each function decorated with `@hook` is registered by name
- Hook names must be unique across all hook files
- Python hook references in MODEL() headers are validated at compile time: unknown names, unknown kwargs, and missing required parameters all raise compile errors

#### Validation

At compile time, SQLBuild validates every `python("hook_name")` reference:

- The hook name must match a discovered `@hook` function
- Any keyword arguments passed in the MODEL() header must match parameters on the function signature
- If the function does not accept `**kwargs`, unknown arguments raise a compile error

### Config reference

#### Common config

| Field | Description |
|-------|-------------|
| `materialized` | `view`, `table`, `incremental`, or a custom materialization name |
| `tags` | List of tags for selector filtering |
| `description` | Human-readable description of the model |
| `columns` | Column declarations with optional types, audits, and descriptions |
| `audits` | Model-level audit instances |
| `schema` | Override target schema |
| `database` | Override target database |
| `alias` | Override target relation name |
| `pre_hooks` | Lifecycle hooks to run before materialization: `sql("...")` and/or `python("hook_name")` entries |
| `post_hooks` | Lifecycle hooks to run after materialization: `sql("...")` and/or `python("hook_name")` entries |
| `enabled` | Set to `false` to skip the model |
| `contract` | `enforced` or `none`. When enforced, declared columns are the authoritative output schema. |
| `sql_validation` | Per-model boolean override of the project `sql_validation` setting |

Four knobs gate compile-time SQL validation, from broadest to narrowest:

1. `settings.sql_analysis` - master switch for all SQL-analysis features
2. `--no-sql-validation` - per-run CLI kill switch
3. `settings.sql_validation` - project-level validation setting
4. `MODEL (sql_validation ...)` - per-model override of the project setting

Validation runs only when every broader knob allows it: `sql_analysis` must be on and `--no-sql-validation` absent before the project/model `sql_validation` values are consulted.

#### Incremental config

| Field | Description |
|-------|-------------|
| `incremental_strategy` | `append`, `delete_insert`, or `merge` |
| `cursor` | Output column used to track incremental position |
| `cursor_type` | `timestamp` or `integer` |
| `cursor_grain` | Time grain for timestamp cursors: `second`, `minute`, `hour`, `day`, `month`, `year` |
| `cursor_start` | Lower bound floor for the cursor |
| `cursor_inputs` | Map of upstream ref/source names to their cursor columns |
| `unique_key` | Column(s) used for merge and delete_insert matching |
| `incremental_mode` | Set to `microbatch` to enable batched execution |
| `batch_size` | Batch window size (e.g. `1d`, `1h`, or an integer) |
| `lookback` | Extend the replay window backwards to re-process recent data |
| `on_schema_change` | `append_new_columns`, `sync_all_columns`, `ignore`, or `fail` |
| `replay_on_change` | `forward` (default), `full`, or `bounded-<duration>` (e.g. `bounded-14d`) |
| `run_despite_unchanged` | Force periodic rebuilds: `always` or a duration (e.g. `24h`, `30d`). Table materializations only. |

See [Incremental](/concepts/incremental) for detailed usage.

#### Custom materialization config

| Field | Description |
|-------|-------------|
| `config` | Arbitrary key-value pairs passed to `ctx.config` in the Python function |
| `placeholders` | Default values for `@@@placeholder` tokens in the SQL |

#### Diff config

| Field | Description |
|-------|-------------|
| `row_diff_exclude_columns` | Columns to exclude from row-level diff comparisons |
| `row_diff_tolerances` | Tolerance rules for numeric diff comparisons |

## Enums and Constants

Source: `concepts/enums-and-constants.mdx`

Declare compiler-validated domain values and scalar constants for use across SQLBuild SQL.

Enums name a fixed domain of string or integer values. Constants name one string or integer value. SQLBuild validates references at compile time and renders them as SQL literals.

### Public declarations

Public declarations are available throughout the project. Put enum files anywhere under `enums/` and constant files anywhere under `constants/`; both roots are discovered recursively.

```sql
-- enums/market/market_type.sql
ENUM (
  name market_type,
  members [WIN, PLACE, SHOW],
);
```

Shorthand members use the member name as the string value. Use explicit members when the reference name and stored value differ, or for integer enums:

```sql
ENUM (
  name source,
  members (
    CENTRUM "centrum",
    PARISTURF "paristurf",
  ),
);

ENUM (
  name priority,
  members (LOW 1, HIGH 3),
);
```

```sql
-- constants/market/thresholds.sql
CONSTANT (name min_runners, value 7);
CONSTANT (name fallback_source, value "centrum");
```

A file may contain multiple declarations. Public names must not start with `_`.

### References

Use `@enum("name").MEMBER` and `@const("name")` anywhere public declarations are supported:

```sql
SELECT *
FROM prices
WHERE market_type = @enum("market_type").WIN
  AND runner_count > @const("min_runners")
```

This compiles to:

```sql
WHERE market_type = 'WIN'
  AND runner_count > 7
```

Public references work in model queries, SQL hooks, SQL functions, audits, unit tests, scenarios, and inline source expressions. Unknown declarations or enum members fail compilation.

### Model-local declarations

Use model-local declarations for values that should not enter the project-wide namespace:

```sql
MODEL (
  enums (
    _state [OPEN, CLOSED],
  ),
  constants (
    _min_runners 7,
  ),
);

SELECT *
FROM runners
WHERE state = @enum("_state").OPEN
  AND runner_count > @const("_min_runners")
```

Model-local names must start with `_`. They are available only in that model's query and SQL hooks; another model cannot resolve them.

### Types and validation

Enums must contain at least one member and use one consistent scalar type. String and integer members cannot be mixed. Integer values use explicit member syntax.

Names must be SQL identifiers. Duplicate declaration names, duplicate member names, invalid visibility prefixes, and malformed references all fail compilation.

### Enum-typed contracts

An enum name can be used as a model column type:

```sql
MODEL (
  contract enforced,
  columns (
    market_type (type market_type),
  ),
);
```

SQLBuild resolves the physical type to `VARCHAR` or `INTEGER`. With `contract enforced`, it also adds an `accepted_values` audit for the enum members, so an out-of-domain value blocks promotion.

Declaration changes participate in change detection. A changed referenced value changes compiled SQL; changed members of an enum-typed contract change the model's contract identity.

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
| `@const("name")` | Executable SQL | Compile time - expands to the named scalar value |
| `@macro(args)` | Model SQL, SQL hooks, tests, audits, inline source expressions | Compile time - expands to macro return value |
| `@@name` | Model SQL, SQL hooks, tests, audits, inline source expressions | Compile time - project variable substitution |
| `@@ENV:NAME` | Model SQL, SQL hooks, tests, audits, inline source expressions | Compile time - environment variable |
| `@@CTX:name` | SQL hooks only | Compile time - destination relation, target, run ID |
| `@@@name` | Model SQL | Preserved for runtime (custom materializations) |
| `@name` / `@'name'` | Generic audit SQL only | Audit engine parameter |
| `${CTX:...}` | TOML/YAML config values | Config compilation |
| `${ENV:...}` | TOML/YAML config values | Config compilation |

`@@CTX:` is intentionally SQL-hook-only. Model SQL describes a relation's data and should not reference its own destination identity. SQL hooks are the operational SQL layer where destination context is useful - grants, logging, post-materialization DDL. Python hooks access the same information through `ctx.destination` on the `HookContext` object (see [Hooks](/concepts/models#hooks)).

See [Enums and Constants](/concepts/enums-and-constants) for declaration syntax, visibility, and contract integration.

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
post_hooks [sql('GRANT SELECT ON @@CTX:destination.qualified TO analyst_role')],
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

Generic audit SQL uses `@name` (single `@`, no parentheses) for audit-engine placeholders. These are resolved by the audit engine, not the compiler:

```sql
SELECT @column
FROM @relation
WHERE @column IS NULL
```

This is distinct from `@@name` (project variables) and `@macro()` (macro calls), so there is no ambiguity. See [Audits](/concepts/audits) for details on generic audit parameters.

### Compilation order

SQLBuild processes authored SQL in this order:

1. **Config templates** (`${CTX:...}`, `${ENV:...}`) in TOML/YAML config values are resolved during config compilation
2. **Project variables** (`@@name`), **environment variables** (`@@ENV:NAME`), and **context variables** (`@@CTX:name` in SQL hooks) are substituted
3. **Enum and constant references** are validated and expanded to scalar SQL literals
4. **Macro calls** (`@name(args)`) are expanded
5. **SQL analysis validation** runs against the fully expanded SQL

This means:
- Config templates resolve first, before any SQL processing
- Macros see already-substituted variable values in the SQL
- `@@CTX:destination.qualified` in SQL hooks sees the final target-overridden destination name because hooks are expanded after destination naming is fully resolved
- SQL analysis validates the final expanded SQL, catching syntax errors from both vars and macros

## Python Macros

Source: `concepts/macros.mdx`

Reusable Python functions that generate SQL fragments at compile time.

Macros are Python functions that generate SQL fragments at compile time. Instead of Jinja templates, you write real Python - testable, debuggable, and composable with standard tooling.

For the full picture of how macros fit into SQLBuild's interpolation system, see [Interpolation](/concepts/interpolation).

### Defining macros

Create Python files under `macros/` in your project. Every public function in a macro file becomes a callable macro:

```python
# macros/currency.py
def cents_to_dollars(column):
    """Convert a cents integer column to a dollars decimal."""
    return f"ROUND(CAST({column} AS DOUBLE) / 100, 2)"
```

Macros can accept any Python arguments (strings, numbers, lists, dicts, booleans) and must return a SQL string when called from SQL.

### Using macros in models

Call macros in model SQL using the `@macro_name(args)` syntax:

```sql
MODEL (
  materialized table,
  tags [marts],
);

SELECT
  CAST(o.ordered_at AS DATE) AS revenue_date,
  COUNT(DISTINCT o.order_id) AS order_count,
  SUM(p.amount_cents) AS total_revenue_cents,
  @cents_to_dollars('SUM(p.amount_cents)') AS total_revenue_dollars
FROM __ref("stg_orders") o
INNER JOIN __ref("stg_payments") p ON o.order_id = p.order_id
GROUP BY CAST(o.ordered_at AS DATE)
```

At compile time, `@cents_to_dollars('SUM(p.amount_cents)')` expands to `ROUND(CAST(SUM(p.amount_cents) AS DOUBLE) / 100, 2)`.

### Using macros in tests

Because unit tests are written in SQL, they support macro calls. This is useful for reusable mock data generators:

```python
# macros/test_helpers.py
def mock_orders(count=1):
    """Generate mock order rows."""
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

### Using macros in hooks

Macros are expanded inside `sql(...)` hook entries in `pre_hooks` and `post_hooks`:

```python
# macros/permissions.py
def grant_target(target):
    return f"GRANT SELECT ON {target} TO analyst_role"
```

```sql
MODEL (
  materialized table,
  post_hooks [sql('@grant_target(@@CTX:destination.qualified)')],
);

SELECT 1 AS id
```

Hook SQL is validated at compile time, so invalid hook SQL is caught before execution. SQL hooks also support `@@CTX:` context variables, `@@name` project variables, and `@@ENV:NAME` environment variables directly without needing a macro wrapper.

For hooks that need more than string interpolation, use `python(...)` hooks instead. See [Hooks](/concepts/models#hooks) for the full Python hook API.

### Macro context

When a macro function accepts a `ctx` parameter as its first argument, SQLBuild passes a `MacroContext` object with adapter and target information:

```python
# macros/datetime.py
def timestamp_trunc(ctx, grain: str, expr: str) -> str:
    if ctx.adapter_name == "bigquery":
        return f"TIMESTAMP_TRUNC({expr}, {grain.upper()})"
    return f"DATE_TRUNC('{grain}', {expr})"
```

The macro context provides:

| Field | Description |
|-------|-------------|
| `adapter_name` | The active adapter (e.g. `duckdb`, `snowflake`) |
| `sql_analysis_enabled` | Whether SQL analysis is enabled |
| `target_name` | The active target name, if any |
| `vars` | Effective project variables as a dict (merged from project config, target, local config, and CLI `--vars`) |

```python
def schema_qualified(ctx, table: str) -> str:
    schema = ctx.vars.get("schema_prefix", "public")
    return f"{schema}.{table}"
```

### Macro arguments

Macro arguments use Python literal syntax. Supported types:

- **Strings:** `'value'` or `"value"`
- **Numbers:** `42`, `3.14`, `-1`
- **Booleans:** `True`, `False`
- **Lists:** `[1, 2, 3]`
- **Dicts:** `{'key': 'value'}`
- **None:** `None`
- **Nested macro calls:** `@other_macro('arg')`

Keyword arguments are supported:

```sql
@mock_orders(count=5, status='completed')
```

#### Nested macro calls in arguments

Macros can be passed as arguments to other macros. The inner macro evaluates first and its result becomes an argument to the outer macro:

```sql
@format_column('revenue', @cents_to_dollars('SUM(amount_cents)'))
```

You can mix regular arguments with nested macro calls:

```sql
@wrap_with_alias(@cents_to_dollars('total_cents'), 'total_dollars')
```

Inner macros used as arguments don't have to return strings - they can return any Python object that the outer macro accepts.

### Composing macros

Macro output cannot contain macro calls. Expansion is single-pass: if a macro returns SQL containing `@another_macro()`, SQLBuild raises an error. If you need composition, compose in Python:

```python
# macros/reporting.py
from macros.currency import cents_to_dollars

def revenue_column(column, alias):
    dollars_expr = cents_to_dollars(column)
    return f"{dollars_expr} AS {alias}"
```

### Where macros are allowed

- **Model query SQL** - the SELECT statement after the MODEL() header
- **Hook strings** - `sql(...)` entries in `pre_hooks` and `post_hooks` in MODEL() config
- **Test SQL** - unit test CTE bodies
- **Audit SQL** - singular audit queries

Macros are **not allowed** in MODEL() config values (other than SQL hook entries). If a config field contains `@macro()`, SQLBuild raises a compile error.

### Discovery rules

- SQLBuild discovers all `.py` files under `macros/` recursively
- Every public function (not starting with `_`) becomes a macro
- Macro names must be unique across all macro files - duplicates raise a compile error
- Macros are loaded once at compile time, not per-model

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

#### Table functions are terminal

Table functions sit at the edge of the DAG, facing the consumer. They can reference models, seeds, sources, and other functions - but models cannot reference table functions. This is enforced at compile time.

The semantic reason: table functions are parameterized queries meant to be called by applications or analysts, not intermediate pipeline steps. Interleaving them into the model DAG would break the clean separation between pipeline computation and consumer-facing access patterns.

#### Using table functions

Table functions are called directly in SQL contexts that support table-valued functions:

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

These references are resolved at compile time and create DAG edges. If a referenced model changes, the function is redeployed.

### Change propagation

Functions participate in fingerprint-based change detection. If a function's SQL body or Python source changes, SQLBuild redeploys the function and marks all dependent models as needing a rebuild.

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

Incremental models process only new or changed data instead of rebuilding the entire table. SQLBuild works out where to resume by reading the highest cursor value (timestamp or integer) already in the target table, so there is no state store or checkpoint to maintain. If a model fails for several runs, the next successful build picks up from the last data it actually wrote, with no manual backfilling.

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

### Cursors

Cursors define the incremental replay boundary. SQLBuild queries `MAX(cursor)` from the target table and `MIN/MAX` from upstream inputs to compute the replay window automatically.

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

SQLBuild uses these to compute `MIN/MAX` across the listed inputs and determine the replay window.

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

## Planning and Change Detection

Source: `concepts/planning.mdx`

How SQLBuild decides what to build: fingerprints, change reasons, and warehouse-native state.

When you run `sqb plan` or `sqb build`, SQLBuild compiles your project, compares it against the current warehouse state, and produces a plan. By default, SQLBuild runs your full selection - the same predictable behavior as a plain build, with nothing to configure.

Change-aware pruning is opt-in and requires [virtual environments](/concepts/virtual-environments). In a virtual environment, pass `--changes-only` (or set `changes_only = true` in config) to narrow the run to only stale work - unchanged models, seeds, audits, and Python nodes are then skipped. The fingerprints and change reasons below are recorded on every successful build regardless, so change detection is ready the moment you enable pruning.

### What is tracked

Every node in the graph has a versioned identity stored in `_sqlbuild_fingerprints` in the target schema. The planner reads these on every run and compares them against the compiled project.

#### Models and functions

Each model and function has a **fingerprint** derived from:

- **Query hash** - the normalized SQL after macro expansion and reference resolution.
- **Config hash** - version-identity config values (materialization settings, contracts, hooks, custom config/placeholders).
- **Function hashes** - for models that depend on user-defined functions, the function's own fingerprint is included. A function change cascades to all dependent models.

#### Seeds

Seeds are fingerprinted by content hash and load-affecting config. Unchanged seeds are not reloaded.

#### Python nodes

Loaders, tasks, assets, checks, and hooks are fingerprinted by source-code hash, transitive project-dependency hashes (scoped to the git root, so third-party package changes don't count), and decorator config.

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

Change-aware pruning requires virtual environments (`virtual_environments = true`); it is rejected in standard mode. Within a virtual environment, `--changes-only` narrows the scope to only models that are actually stale:

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

### Warehouse-native state (standard mode)

In standard mode, all change-tracking state lives in the warehouse as append-only tables in the same schemas as your data:

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

#### Attaching custom generic audits

```sql
MODEL (
  materialized table,
  audits [
    expression_is_true (
      name "revenue is non-negative",
      expression "total_revenue_cents >= 0",
    ),
  ],
);
```

### Singular audits

Singular audits are standalone SQL files under `audits/` (outside the `generic/` directory) that reference models directly. They're useful for one-off checks that don't fit a reusable template.

```sql
-- audits/orders_have_payments.sql
AUDIT ();

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
          name: no future orders
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
      name "orders placed is non-negative",
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
TEST (mode: macro, name: "calculates line total cents");

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
TEST (mode: udf, name: "detects completed orders");

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
TEST (mode: table_fn, name: "returns customer orders");

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
TEST (name: "completed orders only");

WITH
__source__raw__orders AS (
  SELECT 1 AS id, 100 AS customer_id, 'completed' AS status
),
__expected__stg_orders AS (
  SELECT 1 AS order_id, 100 AS customer_id, 'completed' AS status
)
SELECT 1

TEST (name: "cancelled orders excluded");

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
  description: "Daily revenue includes only successful payments",
  tags: ["revenue", "example"]
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

- **two targets** (e.g. `prod:dev`) in standard mode, or
- **two virtual environments** (VDEs) when [virtual environments](/concepts/virtual-environments) are enabled.

The mechanics below are identical for both; only what `FROM` and `TO` refer to changes.

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

## Python Nodes

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

Node results (payload, metadata, status, errors) are persisted after each execution. In standard mode, results are stored in `_sqlbuild_node_results` in the warehouse alongside your data. In virtual mode, results are stored in the VDE state backend scoped per environment. Results persist across runs, so they are available for observability, debugging, and downstream consumption.

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

Names are globally unique across models, sources, seeds, functions, loaders, tasks, assets, and checks.

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

Provider names must be unique across all provider files and must be valid Python identifiers (`lower_snake_case`).

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
# hooks/notify.py
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
- Provider names must be unique across all provider files
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

Virtual environments are opt-in via `virtual_environments = true` (under `[settings]`) and require a state store. Projects that don't need environment isolation or promotion workflows should use the default standard mode.

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

[connection]
database = "warehouse.duckdb"

[targets.dev]
schema = "dev"

[targets.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"

[targets.dev.state.connection]
database = "state.duckdb"
```

The `virtual_environments` setting switches the project from standard mode (default) to virtual mode. All state, plan, build, promote, rollback, and reconcile commands route through the virtual path when this is enabled.

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

Virtual builds create versioned physical relations and update VDE pointer sets. The build lifecycle is the same as standard mode (seeds, tests, models, audits), but model outputs are written to versioned physical tables and exposed through logical VDE views.

Virtual builds run ingress (loaders and Python nodes that feed sources) as a separate phase before SQL model execution. This means independent SQL models that do not depend on loaders will wait for all ingress to complete before starting. Standard mode does not have this limitation. This keeps VDE state persistence simpler and safer but may add wall time when ingress is slow and independent SQL work is available. A future optimization may allow overlapping ingress with independent SQL execution.

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

Virtual environment builds run the full selection by default, like standard mode. Add `--changes-only` to intersect the selection with the stale-driven set, so only models that are both selected and stale are built:

```bash
sqb build --virtual-env pr_123 --select path:models/marts --changes-only
```

This is useful when the stale cascade is large and you want to build a coherent subgraph without running unchanged models. Without `--changes-only`, every selected model is built regardless of state.

Change-aware pruning is opt-in in both standard mode and virtual environments. See [Planning and Change Detection](/concepts/planning) for how fingerprints, source freshness, and identity tracking determine what gets built.

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

Custom materializations are supported in virtual mode. By default, SQLBuild seeds new physical versions using the standard clone/copy strategy before calling the custom `materialize` function.

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

The project can continue operating in standard mode, or you can re-adopt to return to virtual mode.

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

### Comparison with standard-mode clone

In standard mode, `sqb clone` copies model relations between targets using zero-copy cloning where supported. In virtual mode, clone hydrates versioned physical relations instead. The source and target are still physical targets, but the copied objects are physical version relations rather than normal model targets.

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

### Comparison with standard-mode diff

In standard mode, `sqb diff prod:dev` compares physical target schemas and data directly in the warehouse. In virtual mode, `sqb diff dev:pr_123` compares VDE pointer sets within a single physical target, then inspects the physical versions those pointers reference.

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

The project can continue in standard mode or re-adopt to return to virtual mode.

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

### sqb skills update

Write the packaged SQLBuild skill file to agent-specific locations in your project.

```bash
sqb skills update [flags]
```

#### Flags

| Flag | Description |
|------|-------------|
| `--target` | Specify agent targets to install for. Can be passed multiple times. |
| `--global` | Install to global agent config directories instead of project-local |
| `--force` | Overwrite existing skill files even if they were not generated by SQLBuild |

#### Targets

Three agent targets are supported:

| Target | Local path | Global path |
|--------|-----------|-------------|
| `opencode` | `.opencode/skills/sqlbuild/SKILL.md` | `~/.config/opencode/skills/sqlbuild/SKILL.md` |
| `claude` | `.claude/skills/sqlbuild/SKILL.md` | `~/.claude/skills/sqlbuild/SKILL.md` |
| `agents` | `.agents/skills/sqlbuild/SKILL.md` | `~/.agents/skills/sqlbuild/SKILL.md` |

By default, all three targets are installed. Use `--target` to install specific ones:

```bash
# Install for all targets (default)
sqb skills update

# Install for Claude Code only
sqb skills update --target claude

# Install for OpenCode and Claude
sqb skills update --target opencode --target claude

# Install globally
sqb skills update --global
```

#### Overwrite behavior

Generated skill files include a marker comment. `sqb skills update` will:

- Overwrite files it previously generated (safe to rerun)
- Refuse to overwrite files that were manually created or edited (no marker)
- Overwrite any file when `--force` is passed

#### Configuration

Default targets can be set in `sqlbuild_project.toml` so the team shares the same agent config:

```toml
[skills]
targets = ["opencode", "claude"]
```

CLI `--target` flags override the TOML config.

#### Playground

The playground command automatically runs `sqb skills update` after creating the project, so AI agents are ready to use immediately:

```bash
sqb playground waffle-shop
cd waffle-shop
# Agent skill files are already installed
```

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
- **Column contract validation**: If a model declares columns in its `MODEL()` header, compile checks that every declared column exists in the query output. If a column declares a type and `type_enforcement` is enabled, compile also verifies the inferred type matches the declared type
- **Column lineage**: Traces which source columns flow into each output column, including transform classification. See [Column Lineage](/concepts/column-lineage) for details

#### Contract diagnostics

When a contract violation is found, compile reports it with source-annotated diagnostics:

```
error[K001]: required column 'total_cents' missing from model output
  model: fact_orders
  --> models/marts/fact_orders.sql:5:3
  5 | SELECT order_id, customer_id
    |        ^^^^^^^^
  = help: add total_cents to the SELECT list or remove it from MODEL(columns)
```

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
| `--full-refresh` | Plan a full rebuild of all selected models |
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
| `--full-refresh` | Drop and rebuild all selected models from scratch |
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
5. Models are materialized in DAG topological order (unchanged models are skipped)
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

No `manifest.json` is required. Deferred references resolve directly against the live target.

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

Runs SQL unit tests and multi-model tests without building models. Useful for validating test logic independently.

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

### Examples

```bash
# Run all audits
sqb audit

# Run audits for marts only
sqb audit --select path:models/marts
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

To compare against state stored in a virtual environment instead of standard mode state:

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

The origin target must already contain the built relations being cloned. The configured warehouse credentials must be able to read those relations and create relations in the destination. Managed physical sources may bootstrap a destination that has not been built. See [Project Configuration](/concepts/project-configuration) for details.

## diff

Source: `cli/diff.mdx`

Compare schemas and data between targets or virtual environments.

Compares schemas and optionally row-level data between two build contexts: two targets (e.g. `prod:dev`) in standard mode, or two virtual environments when virtual mode is enabled. See [Data Diffs](/concepts/diff) for detailed usage.

### Usage

```bash
sqb diff <FROM>:<TO> <mode> [flags]
```

The first argument is a positional `FROM:TO` range. Exactly one mode is required: `--full`, `--schema-only`, or `--bounded <duration>`.

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

Run SQLBuild alongside an existing dbt project.

## sqb dbt

Orchestrate dbt and SQLBuild together. Each subcommand runs dbt first, then SQLBuild, with selection logic that works across both project graphs. `sqb dbt build`, `sqb dbt run`, and `sqb dbt plan` run the full selection, exactly like dbt. See [Using SQLBuild with dbt](/concepts/dbt-compatibility/overview) for concepts and selection behavior.

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
