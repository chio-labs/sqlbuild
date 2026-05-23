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
- `concepts/dbt-interop`
- `concepts/comparison-with-sqlmesh`
- `concepts/project-configuration`
- `concepts/adapters`
- `concepts/adapters/duckdb`
- `concepts/adapters/motherduck`
- `concepts/adapters/snowflake`
- `concepts/adapters/bigquery`
- `concepts/adapters/databricks`
- `concepts/adapters/postgres`
- `concepts/sources`
- `concepts/loaders`
- `concepts/seeds`
- `concepts/models`
- `concepts/interpolation`
- `concepts/macros`
- `concepts/functions`
- `concepts/incremental`
- `concepts/snapshots`
- `concepts/audits`
- `concepts/testing`
- `concepts/scenarios`
- `concepts/selectors`
- `concepts/column-lineage`
- `concepts/environment-diffs`
- `integrations/dagster`
- `integrations/dagster-reference`
- `integrations/dlt`
- `cli/compile`
- `cli/plan`
- `cli/build`
- `cli/run`
- `cli/test`
- `cli/audit`
- `cli/load`
- `cli/seed`
- `cli/clone`
- `cli/diff`
- `cli/lineage`
- `cli/dag`
- `cli/debug`
- `cli/janitor`
- `cli/query`
- `cli/scenario`
- `cli/dbt`
- `cli/skills`
- `cli/clean`
- `cli/init`
- `cli/playground`

## Introduction

Source: `index.mdx`

Typed, test-first SQL pipelines with local E2E testing.

Validate SQL at compile time, block bad data before promotion, and run full E2E tests with no warehouse required.

### How it works

1. **Define** your models as SQL files with `MODEL()` headers that declare configuration, schema, and audits inline
2. **Compile** to resolve references, validate SQL, infer column types, check contracts, and compute column lineage - all offline
3. **Plan** what needs to change based on fingerprints, schema diffs, and backfill policies
4. **Build** by executing the plan: materializing models, validating data before promotion, and ensuring bad data never reaches production
5. **Test** with chained unit tests, E2E scenario tests, and local replay through DuckDB - no warehouse required

### Why SQLBuild?

#### SQL unit tests that scale

- **Chain across models:** Mock your sources, assert on the model you care about, and SQLBuild automatically resolves every intermediate model using its real SQL. One test file can be a full integration test across your entire pipeline.
- **Macro-powered mocks:** Because unit tests are written in SQL, they support macro calls, so you can write reusable mock generators and fixture builders instead of copy-pasting mock inputs across test files.

```sql
-- Mock two sources, assert on the final mart.
-- stg_orders and stg_payments resolve automatically from their real SQL.
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

#### E2E scenario tests with local replay

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
  SELECT 1 AS payment_id, 1 AS order_id, 1700 AS amount_cents, 'success' AS payment_status
),
__expected__daily_revenue AS (
  SELECT CAST('2026-04-01' AS DATE) AS revenue_date, 1700 AS total_revenue_cents
),
__assert__all_orders_have_payments AS (
  SELECT * FROM __ref("fact_orders") WHERE payment_amount_cents IS NULL
)
SELECT 1
```

#### Audits that block bad data

- **Full table builds:** SQLBuild materializes into a staging table and runs `error`-severity audits before promotion. If any fail, the swap is blocked and the production table is untouched.
- **Incremental models:** Delta-phase audits validate each batch before DML is applied. Bad data is caught before it reaches the target.

#### Python macros, not Jinja

- **Real Python functions:** Testable, debuggable, and composable with standard tooling. No templating language, no string interpolation surprises.

```python
# macros/grant_target.py
def grant_target(target):
    return f"GRANT SELECT ON {target} TO analyst_role"
```

#### Change-aware incremental rebuilds

- **Query-change detection:** Fingerprint-based tracking detects when model SQL has actually changed and triggers bounded or full rebuilds automatically.
- **Backfill cascade:** Upstream query or schema changes propagate rebuild signals downstream through the DAG, with per-model control over rebuild windows.
- **Schema diffs in the plan:** The plan shows column additions, removals, and type changes before anything executes, with configurable policies to block or adapt.
- **Controlled rebuild windows:** `query_change_backfill` and `schema_change_backfill` policies let you choose between full rebuild and bounded replay (e.g. `bounded-14d`).

#### Incremental processing

- **Cursor-based replay:** SQLBuild tracks position using a timestamp or integer column and automatically detects where to resume. If a model fails for several runs, the next successful build replays from where it left off with no manual backfilling.
- **Microbatch mode:** Split large replay windows into configurable batches, each with its own audit cycle. Or process the full range in one pass, the choice is per-model.

#### Multi-environment workflows

- **Environment diffs:** Compare schemas and row-level data between environments with `sqb diff prod:dev`.

- **Zero-copy cloning:** Branch environments instantly with `sqb clone` without duplicating data.
- **Deferred references:** Compile and plan against a production environment with `--defer-to` while building in dev.
- **No manifest required:** Clone, diff, and defer work directly against live environments. No `manifest.json` generation, no artifact management, no stale state.

#### Extensibility

- **Source loaders:** Load external data into source tables with Python functions. Supports incremental write strategies (table, append, delete_insert, merge), cursor-based loading, loader-to-loader dependencies, and concurrent execution. Loaders run automatically during builds.

```python
from sqlbuild.loaders import loader
from sqlbuild.executor.load.models import LoaderContext

@loader
def raw_orders(ctx: LoaderContext):
    if ctx.current_cursor_value is None:
        return fetch_all_orders()
    return fetch_orders_since(ctx.current_cursor_value)
```
- **User-defined functions:** SQL and Python UDFs managed as part of your project. Functions participate in the DAG - definition changes trigger rebuilds of dependent models. Table functions provide predicate-pushdown-friendly alternatives to final-layer views.
- **Custom materializations:** Write materialization logic in Python with full framework integration - including audit hooks, schema change signals, and query change detection.

```python
def materialize(ctx: MaterializationContext) -> MaterializationResult:
    stale = find_untracked_partitions(ctx)

    for partition in stale:
        ctx.adapter.create_table_as(ctx.connection, target=staging, sql=partition_sql)
        ctx.run_audits(staging)  # same audit guarantees as built-in types
        ctx.execute_sql(f"INSERT INTO {ctx.target} SELECT * FROM {staging}")

    return MaterializationResult(relation=ctx.target)
```
- **Path-between selectors:** `--select fact_orders~daily_activity_rollup` selects every model on the shortest path between two nodes, with optional upstream/downstream expansion.

### What's next

- **Virtual environments** - Pointer-based environment promotion without recomputing models
- **Stateful execution** - First-party partition state tracking and interval-aware scheduling
- **Python models** - Define models in Python using Pandas, PySpark, Snowpark, or BigFrames for transformations that don't fit naturally in SQL, with the same testing and audit guarantees as SQL models
- **Broader adapter support** - ClickHouse and Microsoft SQL Server

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
sqb build --select path:marts

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
      test_fact_orders.sql             # multi-model unit test
      test_daily_revenue_chain.sql     # chain test across multiple models
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
- [Testing](/concepts/testing) - write SQL unit tests with chaining and macro support
- [Column Lineage](/concepts/column-lineage) - trace individual columns through your pipeline
- [CLI Reference](/cli/build) - full command reference

## Using SQLBuild with dbt

Source: `concepts/dbt-interop.mdx`

Run SQLBuild models downstream of an existing dbt project without migrating.

SQLBuild can run alongside an existing dbt project. Your dbt models stay in dbt. New models, tests, audits, and scenarios are written in SQLBuild and can reference dbt model outputs directly. No migration required.

### How it works

1. SQLBuild runs `dbt compile` to produce a `manifest.json` with model metadata
2. SQLBuild reads the manifest to understand dbt model names and their qualified warehouse tables
3. SQLBuild models reference dbt models using `__dbt_ref("package", "model")`
4. `sqb dbt plan/run/build/test` orchestrates both sides: dbt runs first, then SQLBuild runs against the dbt outputs

dbt is always invoked as a subprocess - SQLBuild does not reimplement Jinja, profiles, or any dbt internals. It calls the `dbt` CLI for compilation, selection, and execution.

### Setup

#### Project layout

A typical layout has both projects side by side:

```
my-workspace/
  dbt_project/
    dbt_project.yml
    models/
      staging/stg_orders.sql
      marts/fact_orders.sql
    target/
      manifest.json
  profiles/
    profiles.yml
  sqlbuild_project/
    sqlbuild_project.toml
    models/
      marts/downstream_orders.sql
    tests/
      unit/test_downstream_orders.sql
```

#### Configuration

Point SQLBuild at the dbt project in `sqlbuild_project.toml`:

```toml
[dbt]
project_dir = "../dbt_project"
profiles_dir = "../profiles"
target_path = "../dbt_project/target"
```

| Field | Description |
|-------|-------------|
| `project_dir` | Path to the dbt project root (where `dbt_project.yml` lives) |
| `profiles_dir` | Path to the directory containing `profiles.yml` |
| `target_path` | Path to dbt's `target/` directory (where `manifest.json` is written) |
| `target` | dbt target name override (optional) |

Paths can be absolute or relative to the SQLBuild project root.

#### Referencing dbt models

SQLBuild models use `__dbt_ref("package", "model")` to reference dbt model outputs:

```sql
MODEL (
  tags [finance],
  columns (order_id (audits [not_null])),
);

SELECT order_id FROM __dbt_ref("analytics", "fact_orders")
```

This resolves to the qualified warehouse table name from the dbt manifest (e.g. `analytics.fact_orders`). The dbt model becomes an upstream dependency in the combined graph.

SQLBuild models can also reference other SQLBuild models with `__ref()` as usual:

```sql
MODEL (tags [marts]);

SELECT order_id FROM __ref("downstream_orders")
```

### Selection behavior

The `sqb dbt` commands use `--select` and `--exclude` to scope what runs. Selectors work across both dbt and SQLBuild, with the system determining which side owns each selector and how to route work.

#### SQLBuild-recognized selectors

These selectors match SQLBuild models directly:

| Selector | Example | Behavior |
|----------|---------|----------|
| Model name | `fact_orders` | Selects that SQLBuild model. Auto-includes its immediate dbt upstream dependencies. |
| Leading `+` | `+fact_orders` | Selects the model plus walks upstream through both SQLBuild and dbt models. |
| Trailing `+` | `fact_orders+` | Selects the model plus all downstream SQLBuild models. |
| Both `+` | `+fact_orders+` | Full upstream (including dbt) and downstream expansion. |
| Tag | `tag:nightly` | Selects all SQLBuild models with that tag. Auto-includes dbt dependencies. |
| Tag with `+` | `+tag:nightly` | Tag match plus upstream expansion through the combined graph. |
| Path | `path:marts` | Selects SQLBuild models under that directory. dbt-style `path:models/marts` is translated automatically. |
| Path with `+` | `+path:marts` | Path match plus upstream/downstream expansion. |

When a SQLBuild model is selected, its immediate dbt upstream dependencies are always included so dbt can build the tables that SQLBuild models read from.

#### dbt-only selectors

Selectors that SQLBuild does not recognize (like `state:modified`, `package:stripe`, `source:stripe.charges`) are passed to `dbt ls` to resolve:

| Selector | Example | Behavior |
|----------|---------|----------|
| Without `+` | `state:modified` | dbt-only work. No SQLBuild models selected. |
| With trailing `+` | `state:modified+` | SQLBuild runs `dbt ls` to find which dbt models match, then walks downstream into SQLBuild territory. |
| With both `+` | `+state:modified+` | Same downstream expansion, plus upstream dbt expansion. |

This means you can use dbt-native selectors like `state:modified+` to trigger rebuilds of SQLBuild models that depend on changed dbt models. If `dbt ls` returns no matching models, no SQLBuild work is triggered.

#### Exclude

`--exclude` removes matching SQLBuild models from the final selection:

```bash
sqb dbt build --select fact_orders+ --exclude tag:nightly
```

#### Examples

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
sqb dbt build --select path:marts
```

### Execution order

For `sqb dbt run` and `sqb dbt build`:

1. **dbt runs first** - a single `dbt run/build` command executes with the user's selectors merged with any additional dbt models required by selected SQLBuild models
2. **SQLBuild runs second** - selected SQLBuild models execute against the now-built dbt tables

For `sqb dbt test`:

1. **dbt test runs first** - with the user's original selectors
2. **SQLBuild test runs** - unit tests for selected SQLBuild models
3. **SQLBuild audit runs** - audits for selected SQLBuild models

The `test_type:data` and `test_type:unit` selectors from dbt are mapped to SQLBuild equivalents: `test_type:data` runs SQLBuild audits, `test_type:unit` runs SQLBuild unit tests.

### Unit tests with dbt refs

SQLBuild unit tests can mock dbt model dependencies using `__dbt_ref__` fixture CTEs. When a model has a package, use `__dbt_ref__package__model`. When there is no package, use `__dbt_ref__model`:

```sql
TEST();

WITH
__dbt_ref__analytics__fact_orders AS (
  SELECT 1 AS order_id, 100 AS customer_id, 2500 AS amount_cents
),
__expected__downstream_orders AS (
  SELECT 1 AS order_id
)
SELECT 1
```

This mocks the dbt model `analytics.fact_orders` with controlled data, allowing you to test your SQLBuild model without a warehouse connection or a compiled dbt manifest.

### Debug

`sqb dbt debug` runs both dbt's and SQLBuild's diagnostics:

```bash
sqb dbt debug
```

This runs `dbt debug` (verifying dbt project config and warehouse connection) followed by `sqb debug` (verifying SQLBuild project config and connection).

### Prerequisites

- dbt must be installed and available on `PATH`
- Both projects must target the same warehouse and schema/database context

SQLBuild runs `dbt compile` automatically as part of `sqb dbt plan/run/build/test` to produce the manifest. You do not need to compile the dbt project manually.

## Feature Comparison

Source: `concepts/comparison-with-sqlmesh.mdx`

Feature comparison between SQLBuild, dbt, and SQLMesh.

SQLBuild, dbt, and SQLMesh are all SQL pipeline frameworks. They share common ground but differ in design philosophy and feature focus.

### Feature comparison

| Feature | SQLBuild | dbt | SQLMesh |
|---------|----------|-----|---------|
| **Testing** | | | |
| Unit tests with model chaining | Chain across multiple models | YAML-stub, single model | CTE-based, single model |
| Macros as test helpers | Tests are SQL - macros work as reusable fixture generators | No (YAML stubs) | No |
| E2E scenario tests | Fixture worlds with real graph execution | No | No |
| Local E2E replay | Capture from warehouse, replay in DuckDB | No | No |
| Macro / UDF / table function tests | `TEST(mode: macro/udf/table_fn)` | No | No |
| Zero-row assertions | `__assert__` CTEs in tests and scenarios | No | No |
| **Audits** | | | |
| Built-in audits | not_null, unique, accepted_values, relationships | not_null, unique, accepted_values, relationships | Extensive (statistical, string pattern, etc.) |
| Blocking audits | Block promotion from staging table | Tests run after materialization | Block during plan (production untouched); during run, data already written |
| Delta/interval-scoped audits | Per-microbatch audit cycle before DML | No | Audit query filtered to processed intervals for time-range models |
| **Compilation** | | | |
| SQL validation | SQLGlot-based, offline | dbt Fusion (proprietary license) | SQLGlot-based |
| Column-level lineage | Compile-time, fast and rich modes | Post-hoc via docs | Compile-time |
| Column contract validation | Compile-time inference plus runtime enforcement with `contract enforced` | YAML schema contracts at runtime | Schema contracts via plan |
| SQL transpilation | For local E2E replay into DuckDB | No | For cross-dialect model execution |
| Python macros | `@macro()` syntax | No (Jinja only) | SQLMesh macro syntax |
| Jinja support | No (Python macros instead) | Yes (core templating) | Yes |
| **Incremental** | | | |
| Incremental strategies | append, delete_insert, merge, SCD Type 2 | append, delete+insert, merge, snapshots | append, delete_insert (time-range), merge (unique-key), SCD Type 2, partition (stateful) |
| Microbatch execution | Configurable batch sizes with per-batch audits | Microbatch (recent addition) | Batch size support |
| Stateful interval tracking | No - cursor-based (no external state) | No | Yes - tracks which intervals ran |
| SCD Type 2 models | Timestamp and check strategies, historical input, hard deletes | Snapshots (limited) | Built-in |
| **Environments** | | | |
| Virtual environments | No | No | Pointer swaps, no compute cost |
| Environment diffs | Full row-level data comparison | No | Table diff |
| Zero-copy cloning | `sqb clone` | No | No |
| **Models** | | | |
| SQL models | `MODEL()` header with inline config | Jinja-templated SQL + YAML sidecar | `MODEL` DDL |
| Python models | Coming soon | Limited (remote only) | Pandas, PySpark, Snowpark, BigFrames |
| Custom materializations | Python with full framework hooks | Jinja-based | Python-based custom model kinds |
| **dbt** | | | |
| dbt interop | Run alongside dbt - reads manifest, no migration | N/A | Jinja compatibility layer plus own macro system |
| **Sources** | | | |
| Source loaders | Python `@loader` functions with table/append/delete_insert/merge strategies | No (external to dbt) | No (external to SQLMesh) |
| Auto-load during builds | Managed sources loaded before dependent models | No | No |
| Source deferral | `defer_sources_to` reads source data from another environment | No | No |
| **Other** | | | |
| Reference syntax | `__ref()` - parses as valid SQL | `{{ ref() }}` - Jinja template | `model_name` with dependency tracking |
| Adapters | DuckDB, MotherDuck, Snowflake, BigQuery, Databricks, PostgreSQL | 30+ (community adapters) | DuckDB, Snowflake, BigQuery, Databricks, Spark, Redshift, Postgres, Trino, MySQL |
| State requirements | Stateless by default | manifest.json + target/ | Requires state store (local database or PostgreSQL for production) |
| Playground | `sqb playground` | Clone example repo | Example project |
| AI agent skills | `sqb skills update` | No | No |

### Where each tool fits

| Tool | Best for |
|------|----------|
| **SQLBuild** | Test-first SQL pipelines. Chained unit tests, local E2E scenario replay in DuckDB, pre-promotion audit gating, offline compile-time validation, and stateless operation. |
| **dbt** | The most widely adopted SQL transformation framework with the largest adapter and community ecosystem. |
| **SQLMesh** | State-managed pipelines with virtual environments, interval tracking, and cross-dialect transpilation. |

### Not yet in SQLBuild

- **Virtual environments** - pointer-based environment promotion without recomputing models
- **Stateful execution** - first-party partition state tracking and interval-aware scheduling (currently possible via custom materializations)
- **Python models** - Pandas, PySpark, Snowpark, BigFrames
- **Broader adapter support** - ClickHouse and Microsoft SQL Server

## Project Configuration

Source: `concepts/project-configuration.mdx`

Configure your SQLBuild project with sqlbuild_project.toml and sqlbuild_local.toml.

SQLBuild projects are configured with two files in the project root:

- **`sqlbuild_project.toml`** - shared project configuration, committed to version control
- **`sqlbuild_local.toml`** - local developer overrides, gitignored

### sqlbuild_project.toml

A complete example:

```toml
name = "waffle_shop"
adapter = "duckdb"
default_environment = "dev"

[connection]
database = "waffle_shop_control.duckdb"

[settings]
default_audit_severity = "warn"

[defaults]
materialized = "table"

[environments.prod]
schema = "prod"

[environments.dev]
schema = "dev"

[path_defaults."models/staging"]
materialized = "view"
```

#### Required fields

| Field | Description |
|-------|-------------|
| `name` | Project name. Used in fingerprint tracking and manifest generation. |
| `adapter` | Database adapter. Currently `duckdb`, with `snowflake`, `bigquery`, and `databricks` coming soon. |

#### Connection

The `connection` block is passed directly to the adapter. For DuckDB:

```toml
[connection]
database = "my_project.duckdb"
```

Environments can override the connection:

```toml
[environments.prod]
schema = "prod"

[environments.prod.connection]
database = "prod.duckdb"

[environments.dev]
schema = "dev"

[environments.dev.connection]
database = "dev.duckdb"
```

### Environments

Environments let you build to different schemas, databases, or connections from the same project. Each environment can override:

| Field | Description |
|-------|-------------|
| `schema` | Target schema for all models in this environment |
| `database` | Target database for all models in this environment |
| `connection` | Override the base connection config |
| `vars` | Environment-specific project variables |
| `defer_sources_to` | Environment name to read managed source data from (see [Loaders](/concepts/loaders#source-deferral)) |
| `clone` | Clone policy (see below) |

```toml
[environments.prod]
schema = "prod"

[environments.prod.vars]
source_schema = "raw_prod"

[environments.dev]
schema = "dev"

[environments.dev.vars]
source_schema = "raw_dev"

[environments.staging]
schema = "staging"

[environments.staging.connection]
database = "staging.duckdb"
```

#### Selecting an environment

The active environment is determined by (in order of precedence):

1. `sqlbuild_local.toml` `environment` field (highest priority)
2. `default_environment` in `sqlbuild_project.toml`
3. No environment (models build to default schema)

#### Clone policies

Environments can declare whether they allow cloning to or from:

```toml
[environments.prod]
schema = "prod"

[environments.prod.clone]
allow_as_source = true
allow_as_target = false

[environments.dev]
schema = "dev"

[environments.dev.clone]
allow_as_source = false
allow_as_target = true
```

### Defaults

Project-wide model defaults. Any field you can set in a `MODEL()` header can be set here as a default:

```toml
[defaults]
materialized = "table"
incremental_strategy = "delete_insert"
query_change_backfill = "full"
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
query_change_backfill = "full"
```

Path matching uses the model's relative file path. A model at `models/staging/stg_orders.sql` matches the `models/staging` path default.

#### Config layering order

Configuration is layered in this order, with later layers overriding earlier ones:

1. **Project defaults** (`defaults`)
2. **Path defaults** (`path_defaults`) - if the model's path matches
3. **MODEL() header** - the model's own config

Tags are special: they are *unioned* across layers rather than overridden. A model with `tags [marts]` in its header that matches a path default with `tags [managed]` will have both tags.

### Settings

Global feature toggles:

```toml
[settings]
sqlglot = true
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
| `sqlglot` | `true` | Enable SQLGlot-based SQL validation and static analysis at compile time |
| `query_change_tracking` | `true` | Track query fingerprints for change detection |
| `sql_validation` | `true` | Validate SQL syntax during compilation |
| `concurrency` | `1` | Maximum parallel model execution (currently serial only) |
| `auto_load_sources` | `true` | Automatically run source loaders before building dependent models during `sqb build` and `sqb run`. See [Loaders](/concepts/loaders). |
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

Environment-specific variables override project-level ones:

```toml
[vars]
schema_prefix = "analytics"

[environments.prod.vars]
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

Paths can be absolute or relative to the SQLBuild project root. See [dbt Interop](/concepts/dbt-interop) for setup and usage details.

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

Local developer overrides. This file should be gitignored.

```toml
environment = "dev"

[connection]
database = "my_local.duckdb"

[settings]
sql_validation = false
concurrency = 4

[vars]
debug_mode = "true"
```

| Field | Description |
|-------|-------------|
| `environment` | Override which environment is active for this developer |
| `adapter` | Override the database adapter (e.g. use DuckDB locally while prod uses Snowflake) |
| `connection` | Override connection config (merged on top of project + environment connection) |
| `settings` | Override global settings (only explicitly set fields take effect) |
| `vars` | Developer-specific variable overrides (merged on top of project + environment vars) |

This replaces the common dbt pattern of switching profiles or setting environment variables to change targets. Each developer sets their environment, connection, and preferences once in `sqlbuild_local.toml` and it persists across sessions.

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
| ClickHouse | Coming soon | |
| Microsoft SQL Server | Coming soon | |

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
    sqlglot_dialect_name = "postgres"  # SQLGlot dialect for SQL validation and lineage

    def connect(self, config):
        ...

    def execute(self, connection, sql):
        ...

    def close(self, connection):
        ...
```

Set `sqlglot_dialect_name` to the [SQLGlot dialect](https://github.com/tobymao/sqlglot/tree/main/sqlglot/dialects) that matches your engine's SQL syntax. This enables compile-time SQL validation, column inference, column lineage, and local scenario replay for your adapter. If omitted, SQLBuild uses generic SQL parsing.

For full control with no inherited defaults, subclass `StrictAdapter` instead. Every method is abstract and must be implemented explicitly. SQLBuild raises a clear error listing any unimplemented methods.

#### Discovery rules

- SQLBuild discovers all `.py` files under `adapters/` recursively (excluding `__init__.py` and files starting with `_`)
- Each file is scanned for classes that define a string `adapter_name` and subclass `StrictAdapter` (or any of its subclasses like `BaseAdapter` or a built-in adapter)
- Adapter names must be unique across all adapter files - duplicates raise an error
- Custom adapter names cannot shadow built-in names (`duckdb`, `snowflake`, `bigquery`, `databricks`)

#### Adapter class hierarchy

```
StrictAdapter          (fully abstract - all methods must be implemented)
  └── BaseAdapter      (ANSI SQL defaults - override only what differs)
        ├── DuckDbAdapter
        ├── SnowflakeAdapter
        ├── BigQueryAdapter
        └── DatabricksAdapter
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

### Per-environment connections

Use environments to separate production and development databases on MotherDuck:

```toml
adapter = "motherduck"

[connection]
token = "${ENV:MOTHERDUCK_TOKEN}"

[environments.prod]
schema = "prod"

[environments.prod.connection]
database = "prod_db"

[environments.dev]
schema = "dev"

[environments.dev.connection]
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

### Per-environment connections

Use environments to connect to different Snowflake databases or warehouses:

```toml
adapter = "snowflake"

[connection]
account = "my_org-my_account"
user = "my_user"
password = "my_password"

[environments.prod]
schema = "prod"

[environments.prod.connection]
role = "PROD_ROLE"
warehouse = "PROD_WH"
database = "PROD_DB"

[environments.dev]
schema = "dev"

[environments.dev.connection]
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

### Per-environment connections

```toml
adapter = "postgres"

[connection]
host = "localhost"
user = "my_user"
password = "${ENV:PG_PASSWORD}"

[environments.prod]
schema = "prod"

[environments.prod.connection]
host = "prod-db.example.com"
dbname = "analytics"

[environments.dev]
schema = "dev"

[environments.dev.connection]
dbname = "analytics_dev"
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

Sources can be loaded by Python functions instead of pointing at existing tables or inline expressions. Add a `loader` field to bind a source to a loader function, and SQLBuild will call it to populate the source table:

```yaml
sources:
  - name: raw_customers
    loader: raw_customers
    write_strategy: table
    columns:
      - name: id
        type: INTEGER
      - name: name
        type: VARCHAR
```

Managed sources support incremental write strategies (`table`, `append`, `delete_insert`, `merge`), cursor-based loading, and concurrent execution.

See [Loaders](/concepts/loaders) for the full guide on writing loader functions, write strategies, the loader context API, and auto-load behavior during builds.

### Config reference

| Field | Description |
|-------|-------------|
| `name` | Source name, used in `__source("name")` references |
| `database` | Target database (optional) |
| `schema` | Target schema (optional) |
| `table` | Target table name (defaults to `name` if omitted) |
| `expression` | Inline SQL expression (alternative to table reference) |
| `loader` | Name of a loader function to bind (see [Loaders](/concepts/loaders)) |
| `write_strategy` | How the loader writes data: `table`, `append`, `delete_insert`, or `merge` |
| `cursor_column` | Column for incremental cursor tracking (required for `delete_insert` and `merge`) |
| `unique_key` | Merge key column(s) (required for `merge`) |
| `description` | Human-readable description |
| `type_enforcement` | Override implicit type enforcement (`true`/`false`). Defaults to `true` when any column declares a type. |
| `contract` | `enforced` or `none`. When enforced, downstream models validate configured column references against source columns. |
| `columns` | Column declarations with optional types and audits |
| `audits` | Source-level audits |

## Loaders

Source: `concepts/loaders.mdx`

Load external data into source tables with Python functions.

Loaders are Python functions that load data into source tables. They replace expression sources and manual ETL scripts with code that lives inside your project, runs as part of the build, and supports incremental write strategies.

### How it works

1. Write a Python function under `loaders/` decorated with `@loader`
2. Bind it to a source in `sources/*.yml` with the `loader` field
3. SQLBuild calls the function, writes returned rows to a staging table, then applies the configured write strategy to the target

Loaders participate in the build lifecycle. When `sqb build` runs, managed sources are loaded before any dependent model is materialized.

### Defining a loader

Place Python files under `loaders/` in your project directory. Each file can contain one or more loader functions:

```python
# loaders/raw_sources.py
from sqlbuild.loaders import loader
from sqlbuild.executor.load.models import LoaderContext

@loader
def raw_customers(ctx: LoaderContext):
    return [
        {"id": 1, "name": "Leslie Knope", "email": "leslie@pawnee.gov"},
        {"id": 2, "name": "Ron Swanson", "email": "ron@pawnee.gov"},
    ]
```

The function receives a `LoaderContext` and returns rows as a list of dicts, an iterator of dicts, or `None` for self-managed loaders.

### Binding to a source

Connect the loader to a source in `sources/*.yml`:

```yaml
sources:
  - name: raw_customers
    loader: raw_customers
    write_strategy: table
    columns:
      - name: id
        type: INTEGER
      - name: name
        type: VARCHAR
      - name: email
        type: VARCHAR
```

The `loader` field references the function name. The source is now a **managed source** - SQLBuild owns both the loading and the schema.

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
    loader: countries
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
    loader: webhook_events
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
    loader: order_events
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

The loader receives `ctx.current_cursor_value` with the current `MAX(cursor_column)` from the target, so it can fetch only new or updated data:

```python
@loader
def order_events(ctx: LoaderContext):
    if ctx.current_cursor_value is None:
        return fetch_all_events()
    return fetch_events_since(ctx.current_cursor_value)
```

#### merge

Upsert based on `unique_key`. Requires both `unique_key` and `cursor_column`.

```yaml
sources:
  - name: raw_customers
    loader: customers
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
def raw_status(ctx: LoaderContext):
    ctx.execute_sql(f"DROP TABLE IF EXISTS {ctx.target}")
    ctx.execute_sql(
        f"CREATE TABLE {ctx.target} AS "
        "SELECT 1 AS status_id, 'loaded' AS status_name"
    )
```

Self-managed loaders must not declare a `write_strategy` in the source YAML. They are useful when you want to use adapter-specific SQL (e.g. `COPY INTO`, external tables), call an external ingestion tool like [dlt](/integrations/dlt), or handle writes in a way that doesn't fit the dict-return pattern.

### Loader context

Every loader function receives a `LoaderContext` as its first argument. It provides access to the target relation, cursor state, environment, and helper methods.

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `target` | `str` | Fully-qualified target relation name |
| `target_database` | `str \| None` | Target database |
| `target_schema` | `str \| None` | Target schema |
| `target_name` | `str` | Unqualified target table name |
| `current_cursor_value` | `object \| None` | Current `MAX(cursor_column)` from the target, or `None` if the table does not exist or has no cursor column |
| `run_id` | `str` | Unique identifier for this execution run |
| `environment` | `str \| None` | Active environment name |
| `vars` | `dict` | Project variables (merged from project, environment, and local config) |
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
| `qualify_name(name)` | Return a fully-qualified relation name in the target database/schema |
| `loader(loader_fn)` | Return a `LoaderRelationRef` for an upstream loader dependency |
| `source(source_name)` | Return a `LoaderRelationRef` for a project source by YAML name |

#### LoaderRelationRef

Returned by `ctx.loader()` and `ctx.source()`. Provides access to an upstream relation:

| Property / Method | Description |
|-------------------|-------------|
| `target` | Fully-qualified relation name |
| `current_cursor_value` | Current `MAX(cursor_column)` from the relation |
| `max(column)` | Return the `MAX` of any column from the relation |

### Loader dependencies

Loaders can depend on other loaders using `depends_on`. Dependencies are executed first, and their target relations are available via `ctx.loader()`:

```python
from sqlbuild.loaders import loader
from sqlbuild.executor.load.models import LoaderContext

@loader
def raw_accounts(ctx: LoaderContext):
    return [
        {"account_id": 1, "account_name": "Pawnee Parks"},
        {"account_id": 2, "account_name": "Eagleton"},
    ]

@loader(depends_on=[raw_accounts])
def raw_account_metrics(ctx: LoaderContext):
    accounts = ctx.loader(raw_accounts)
    rows = ctx.query(f"SELECT account_id FROM {accounts.target}")
    return [
        {"account_id": row[0], "metric": "active"}
        for row in rows.fetchall()
    ]
```

Dependencies form a DAG. SQLBuild schedules loaders in topological order and executes independent loaders concurrently when `--concurrency` is set.

Intermediate loaders (those referenced only via `depends_on` without a source binding) are given synthetic source entries and write to `__loader__<name>` tables by default. Use the `target` parameter on the decorator to override:

```python
@loader(target="staging.shared_accounts")
def raw_accounts(ctx: LoaderContext):
    ...
```

### Decorator parameters

The `@loader` decorator accepts optional parameters that can also be set in the source YAML. When both are specified, the YAML takes precedence.

| Parameter | Description |
|-----------|-------------|
| `depends_on` | List of loader functions this loader depends on |
| `target` | Override the target relation name (can include schema or database) |
| `write_strategy` | `table`, `append`, `delete_insert`, or `merge` |
| `cursor_column` | Column used for incremental cursor tracking |
| `unique_key` | Column(s) used as the merge key (string or list of strings) |
| `columns` | Column specifications with name, type, nullable, and description |
| `contract` | `enforced` or `none` |

### Auto-load during builds

By default, `sqb build` and `sqb run` automatically load managed sources before building dependent models. This is controlled by the `auto_load_sources` setting:

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

When using environments, loaders write data into the active environment. But models may need to read source data from a different environment (e.g. reading production data while developing in dev). The `defer_sources_to` field controls this:

```toml
[environments.dev]
schema = "dev"
defer_sources_to = "prod"

[environments.prod]
schema = "prod"
```

With this config, models in the `dev` environment read managed source data from `prod` schema, even though `sqb load` writes to `dev`. This prevents accidentally reading empty or partial source tables during development.

If an environment uses managed sources but does not declare `defer_sources_to`, SQLBuild raises an error rather than guessing.

### Schema evolution

When a loader returns rows with columns not present in the existing target table, SQLBuild detects the schema change and adds the new columns automatically. Type mismatches between the staging table and the existing target raise an error.

### Project structure

```
my-project/
  loaders/
    raw_sources.py          # loader functions
    api_sources.py           # more loader functions
  sources/
    raw.yml                  # source declarations with loader bindings
  models/
    staging/
      stg_customers.sql      # __source("raw_customers")
```

SQLBuild discovers all `.py` files under `loaders/` recursively (excluding `__init__.py` and files starting with `_`). Each file is scanned for functions decorated with `@loader`.

### Config reference

#### Source YAML fields for managed sources

| Field | Description |
|-------|-------------|
| `loader` | Name of the loader function to bind |
| `write_strategy` | `table`, `append`, `delete_insert`, or `merge` |
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

Pre-hooks and post-hooks execute SQL before and after materialization. They support macro expansion and context variable interpolation:

```sql
MODEL (
  materialized table,
  post_hook ['GRANT SELECT ON @@CTX:target.qualified TO analyst_role'],
);
```

Available context variables in hooks:

| Variable | Value |
|----------|-------|
| `@@CTX:target.qualified` | Fully qualified target relation name |
| `@@CTX:target.schema` | Target schema |
| `@@CTX:target.name` | Target relation name |
| `@@CTX:model_name` | Model name |
| `@@CTX:environment` | Current environment name |
| `@@CTX:run_id` | Current run ID |

Hooks also support macro calls and project variable interpolation (`@@name`, `@@ENV:NAME`).

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
| `pre_hook` | SQL statements to execute before materialization |
| `post_hook` | SQL statements to execute after materialization |
| `enabled` | Set to `false` to skip the model |
| `contract` | `enforced` or `none`. When enforced, declared columns are the authoritative output schema. |

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
| `query_change_backfill` | `full` or `bounded-14d` (hyphenated duration) |
| `schema_change_backfill` | Per-change-type backfill policies (e.g. `add_column bounded-7d`, `type_change full`) |

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

## Interpolation

Source: `concepts/interpolation.mdx`

How SQLBuild processes variables, context, and dynamic content in SQL and config.

SQLBuild uses two syntax layers for dynamic content:

- **`@` syntax** is for any executable SQL - model queries, hooks, tests, audits, and inline source expressions
- **`${...}` syntax** is for config values - project TOML config, MODEL() header fields (excluding hooks), and source/seed YAML declarations

The rule is simple: if it's any SQL that will be executed, it uses `@`. If it's a config value, it uses `${...}`. These layers never mix.

### Syntax reference

| Syntax | Where | Resolved |
|--------|-------|----------|
| `@macro(args)` | Model SQL, hooks, tests, audits, inline source expressions | Compile time - expands to macro return value |
| `@@name` | Model SQL, hooks, tests, audits, inline source expressions | Compile time - project variable substitution |
| `@@ENV:NAME` | Model SQL, hooks, tests, audits, inline source expressions | Compile time - environment variable |
| `@@CTX:name` | Hooks only | Compile time - target relation, environment, run ID |
| `@@@name` | Model SQL | Preserved for runtime (custom materializations) |
| `@name` / `@'name'` | Generic audit SQL only | Audit engine parameter |
| `${CTX:...}` | TOML/YAML config values | Config compilation |
| `${ENV:...}` | TOML/YAML config values | Config compilation |

`@@CTX:` is intentionally hook-only. Model SQL describes a relation's data and should not reference its own target identity. Hooks are the operational SQL layer where target context is useful - grants, logging, post-materialization DDL.

### Project variables

Project variables use `@@name` syntax in SQL and are defined in `sqlbuild_project.toml` or per-environment:

```toml
# sqlbuild_project.toml
[vars]
schema_prefix = "analytics"

[environments.prod.vars]
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

Context variables provide access to the current model's target relation, environment, and run metadata.

**In hooks** (`@@CTX:` syntax):

```sql
post_hook ['GRANT SELECT ON @@CTX:target.qualified TO analyst_role'],
```

**In TOML/YAML config values** (`${CTX:...}` syntax):

```toml
[environments.prod]
schema = "${CTX:target.schema}"
```

Available context variables:

| Variable | Value |
|----------|-------|
| `target.qualified` | Fully qualified target relation name |
| `target.schema` | Target schema |
| `target.name` | Target relation name |
| `model_name` | Model name |
| `environment` | Current environment name |
| `run_id` | Current run ID |

**In macros**, the `MacroContext` object is passed as the first argument when a macro function accepts a `ctx` parameter:

```python
def timestamp_trunc(ctx, grain: str, expr: str) -> str:
    if ctx.adapter_name == "bigquery":
        return f"TIMESTAMP_TRUNC({expr}, {grain.upper()})"
    return f"DATE_TRUNC('{grain}', {expr})"
```

The macro context provides `adapter_name`, `sqlglot_enabled`, `environment_name`, and `vars`.

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
2. **Project variables** (`@@name`), **environment variables** (`@@ENV:NAME`), and **context variables** (`@@CTX:name` in hooks) are substituted
3. **Macro calls** (`@name(args)`) are expanded
4. **SQLGlot validation** runs against the fully expanded SQL

This means:
- Config templates resolve first, before any SQL processing
- Macros see already-substituted variable values in the SQL
- `@@CTX:target.qualified` in hooks sees the final environment-overridden target name because hooks are expanded after target naming is fully resolved
- SQLGlot validates the final expanded SQL, catching syntax errors from both vars and macros

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

Macros are expanded inside `pre_hook` and `post_hook` strings:

```python
# macros/permissions.py
def grant_target(target):
    return f"GRANT SELECT ON {target} TO analyst_role"
```

```sql
MODEL (
  materialized table,
  post_hook ['@grant_target(@@CTX:target.qualified)'],
);

SELECT 1 AS id
```

Hook SQL is validated at compile time using SQLGlot, so invalid hook SQL is caught before execution. Hooks also support `@@CTX:` context variables, `@@name` project variables, and `@@ENV:NAME` environment variables directly without needing a macro wrapper.

### Macro context

When a macro function accepts a `ctx` parameter as its first argument, SQLBuild passes a `MacroContext` object with adapter and environment information:

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
| `sqlglot_enabled` | Whether SQLGlot analysis is enabled |
| `environment_name` | The active environment name, if any |
| `vars` | Effective project variables as a dict (merged from project config, environment, local config, and CLI `--vars`) |

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
- **Hook strings** - `pre_hook` and `post_hook` values in MODEL() config
- **Test SQL** - unit test CTE bodies
- **Audit SQL** - singular audit queries

Macros are **not allowed** in MODEL() config values (other than hooks). If a config field contains `@macro()`, SQLBuild raises a compile error.

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

Incremental models process only new or changed data instead of rebuilding the entire table. SQLBuild tracks position using a cursor column (timestamp or integer) and automatically detects where to resume. If a model fails for several runs, the next successful build replays from where it left off with no manual backfilling.

### Strategies

#### append

Inserts new rows without modifying existing data. Optionally uses a cursor to track position and avoid reprocessing the full source on every run.

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

Append without a cursor is also valid -- the model simply inserts all rows from the source query on every run.

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
| `cursor_start` | Lower bound floor -- the cursor will never replay before this value |
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

SQLBuild uses these to compute `MIN/MAX` across all upstream inputs and determine the replay window.

#### Lookback

Lookback extends the start of the replay window backwards to re-process recent data. This is useful for handling late-arriving records:

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

When a downstream microbatch model depends on an upstream model with a coarser time grain, SQLBuild automatically widens the replay window to the largest participating grain. For example, an hourly model downstream of a daily model will process in day-sized batches to prevent empty windows:

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

-- Downstream: hourly grain, but widens to day automatically
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

### Backfill policies

#### query_change_backfill

Controls what happens when the model SQL changes between runs. SQLBuild detects query changes via fingerprint-based tracking.

| Value | Effect |
|-------|--------|
| `full` | Full table rebuild when query changes |
| `bounded-14d` | Rebuild the last 14 days of data |
| *(omitted)* | Warn only; no automatic rebuild |

The bounded duration supports `d` (days), `h` (hours), `m` (minutes), and `s` (seconds). For example: `bounded-7d`, `bounded-24h`, `bounded-30m`.

```sql
MODEL (
  ...
  query_change_backfill full,
);
```

#### schema_change_backfill

Controls response to schema differences between expected and warehouse columns, with per-change-type policies:

```sql
MODEL (
  ...
  schema_change_backfill (
    add_column bounded-7d,
    type_change full,
  ),
);
```

#### on_schema_change

Controls how schema differences are handled at execution time:

| Value | Effect |
|-------|--------|
| `append_new_columns` | Add new columns to the target table (default) |
| `sync_all_columns` | Add, drop, and alter columns to match the delta |
| `ignore` | Log and continue without schema changes |
| `fail` | Reject the build with an error |

### Cascade behavior

When an upstream model has a backfill policy and its query or schema changes, the backfill signal cascades to all downstream incremental models. The plan shows these as `Upstream changed` with the root cause and effective rebuild window.

Downstream models can override the cascaded behavior by setting their own `query_change_backfill` or `schema_change_backfill` policies. If a downstream model has its own policy, that takes precedence over the cascaded signal. If it has no policy, it inherits the upstream's rebuild scope.

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

SQL unit tests with model chaining, macro support, assertions, and multi-model integration testing.

SQLBuild supports SQL-native unit tests that validate model logic by comparing actual query results against expected values. Tests can chain across multiple models, use macros for reusable mock data, include zero-row assertions, and run as full integration tests across your pipeline.

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

### Chaining across models

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

When a model uses macros that you want to control in tests (e.g. environment-specific logic, dynamic SQL generation), you can override their output with `__macro__<name>` CTEs:

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
- Testing models that use environment-specific macros without depending on environment config
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
    test_daily_revenue_chain.sql      # chain test across multiple models
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

#### Inspecting with --retain

When a scenario fails or you want to inspect intermediate state:

```bash
sqb scenario test daily_revenue_minimal --retain
```

This keeps all scenario-owned relations in the warehouse and prints a relation map showing the logical-to-physical name mapping. You can then query the scenario tables directly to debug.

Runtime artifacts (fixture SQL, model lifecycle SQL, check SQL, cleanup SQL) are always written to `target/run/scenarios/<scenario_name>/` regardless of `--retain`.

### Local scenario testing

Scenarios can run locally against DuckDB using captured JSONL snapshots - no warehouse connection needed. This is useful for CI pipelines and fast developer iteration.

#### Capture

First, capture scenario inputs from the real warehouse:

```bash
sqb scenario capture daily_revenue_minimal
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
4. Transpiles model and check SQL from the project adapter dialect to DuckDB via SQLGlot
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

When SQLGlot's automatic warehouse-to-DuckDB type conversion produces an incompatible type, you can override it in `sqlbuild_project.toml`:

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
- Local replay transpiles SQL from the project adapter dialect to DuckDB via SQLGlot. Adapter-specific SQL that SQLGlot cannot translate will produce a clear error with the failing resource name and reason.

## Selectors

Source: `concepts/selectors.mdx`

Target specific models, paths, tags, or DAG subsets with --select and --exclude.

Selectors let you scope commands to specific subsets of your project. They work with `plan`, `build`, `run`, `test`, `audit`, `seed`, `clone`, and `diff`.

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
sqb build --select path:marts
sqb build --select /marts
sqb build --select marts/
sqb build --select path:intermediate
```

Any name containing `/` is treated as a path selector. `path:marts`, `/marts`, and `marts/` all work the same way. Nested paths work too: `staging/orders`. The `models/` prefix is stripped automatically, so use `path:marts` not `path:models/marts`.

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
sqb build --select path:staging+
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
sqb build --select "tag:staging,path:finance"
```

This selects only models that match *both* conditions - in this case, models tagged `staging` that are also under the `finance` directory.

### Combining select and exclude

```bash
# Build all marts except daily_revenue
sqb build --select path:marts --exclude daily_revenue

# Build everything upstream of fact_orders, excluding staging models
sqb build --select +fact_orders --exclude tag:staging
```

### Error handling

Unknown model names, empty paths, and malformed selectors produce clear error messages:

```
Unknown selector name 'nonexistent_model'
No models found under path 'nonexistent'.
No models found with tag 'nonexistent_tag'
Path selector 'fact_orders~' requires names on both sides of '~'
```

If a path selector accidentally includes the `models/` prefix, SQLBuild suggests the correct form:

```
No models found under path 'models/marts'. (the 'models/' prefix is stripped automatically — try 'path:marts')
```

## Column Lineage

Source: `concepts/column-lineage.mdx`

Trace individual columns through your SQL pipeline - understand where data comes from and where it goes.

### Why column lineage matters

**Impact analysis** - Before changing a source column, see exactly which downstream models and columns are affected. A rename or type change in `raw__orders.id` can be traced through every model that consumes it, even indirectly.

**Debugging data issues** - When a column has unexpected values, trace it upstream to find where the data originates and what transformations it passes through. Instead of reading SQL files and mentally joining dependencies, ask SQLBuild to show the path.

**Documentation** - Column lineage provides machine-readable metadata about your pipeline. The JSON output can feed data catalogs, governance tools, or custom dashboards.

### How it works

SQLBuild analyzes column lineage statically at compile time using [SQLGlot](https://github.com/tobymao/sqlglot). No warehouse connection is needed. The analyzer parses each model's SQL, resolves `ref()` and `source()` calls, and traces columns through `SELECT` lists, CTEs, JOINs, subqueries, and expressions.

Column lineage requires SQLGlot to be enabled in project settings (it is by default).

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

**Rich mode** uses SQLGlot's lineage module and optimizer to resolve columns through CTEs, subqueries, and multi-level nesting with full transform classification. Thorough, but slower because the optimizer runs per column per model.

**Fast mode** parses the SQL AST directly to extract column mappings, resolve CTE references, and classify transforms. It handles the same SQL patterns that most column lineage tools support and is fast enough to run on every compile.

`sqb compile` defaults to fast mode because it runs frequently and analyzes the entire project. `sqb lineage` defaults to rich mode because it targets a specific column in a scoped slice of the DAG, where the deeper analysis is worth the cost. Both are overridable:

```bash
sqb compile --lineage-mode rich
sqb lineage fact_orders.total_cents --mode fast
```

### Using column lineage

#### Interactive tracing with `sqb lineage`

Trace a specific column upstream or downstream:

```bash
# Where does this column come from?
sqb lineage fact_orders.total_cents

# What consumes this column?
sqb lineage fact_orders.order_id --direction downstream

# Limit to 1 hop
sqb lineage fact_orders.total_cents --depth 1

# JSON output
sqb lineage fact_orders.total_cents --format json
```

The target syntax is `model_name.column_name`. Column lineage supports `upstream` and `downstream` directions (not `both` - model lineage supports `both`).

See the [lineage CLI reference](/cli/lineage) for full flag documentation and output format examples.

#### Batch analysis with `sqb compile`

Every compile run includes column lineage in the output:

```bash
# Default: fast column lineage
sqb compile

# Rich column lineage in compile
sqb compile --lineage-mode rich

# Skip column lineage
sqb compile --lineage-mode none

# JSON report includes per-model lineage summary
sqb compile --json
```

In the JSON compile report, each model includes a `lineage` field with `column_count`, `edge_count`, and `has_star` metadata.

See the [compile CLI reference](/cli/compile) for details on the compile report format.

#### Integration with contract validation

Column lineage feeds into compile-time contract validation. When a model declares columns in its `MODEL()` header, the compiler uses inferred column information to check that:

- Every declared column exists in the query output
- Column types match the declared types (when `type_enforcement` is enabled)

These checks run automatically during `sqb compile` and report diagnostics with source-annotated error messages.

### Limitations

- Column lineage requires SQLGlot to be enabled (`sqlglot = true` in settings, which is the default)
- Complex SQL patterns (deeply nested correlated subqueries, dynamic SQL, adapter-specific functions) may reduce accuracy or confidence
- `SELECT *` is tracked as a `star` transform - the analyzer knows the column passes through but the mapping is less precise than explicit column references
- Column lineage is computed statically from SQL text. Runtime-only column additions (e.g. from dynamic UDFs) are not tracked

## Environment Diffs

Source: `concepts/environment-diffs.mdx`

Compare schemas and data between environments to validate changes before promotion.

SQLBuild can compare schemas and row-level data between any two environments. This lets you validate that changes in dev produce the expected results before promoting to production.

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
- Row counts for each environment
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

Rows are matched between environments using the model's `unique_key`. For models without a `unique_key`, SQLBuild uses all columns as a composite key.

The diff output categorises rows as:
- **Equal** - same key, same values in both environments
- **Unequal** - same key, different values (with per-column breakdown)
- **Left only** - exists in the FROM environment but not TO
- **Right only** - exists in the TO environment but not FROM

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

Columns that are expected to differ between environments (like timestamps or environment-specific values) can be excluded from the row comparison:

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
sqb diff prod:dev --schema-only --select path:marts

# Diff models with a specific tag
sqb diff prod:dev --full --select tag:acceptance
```

### Exit codes

`sqb diff` returns exit code `0` when all selected models have no differences, and `1` when any model has schema or row differences. This makes it usable in CI pipelines as a validation gate.

## Overview

Source: `integrations/dagster.mdx`

Orchestrate SQLBuild pipelines with Dagster scheduling, retries, and asset UI.

SQLBuild includes a Dagster integration that maps your project's models, sources, seeds, functions, tests, audits, and scenarios into Dagster assets and asset checks. SQLBuild handles the SQL transformation layer. Dagster handles scheduling, retries, alerting, and the asset-centric UI.

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
2. `@sqlbuild_assets()` reads the artifact and creates one Dagster `AssetSpec` per source, seed, model, and function, with dependency edges preserved
3. `SqlBuildCliResource` shells out to `sqb build`, `sqb test`, `sqb scenario test`, etc. as subprocesses
4. Execution results (materializations, audit pass/fail, scenario outcomes) are parsed from structured JSON and emitted as Dagster `MaterializeResult` and `AssetCheckResult` events

SQLBuild tests and audits become Dagster asset checks. Scenarios become asset checks attached to the models they exercise.

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

Dagster discovers every SQLBuild model as an asset. Selecting a subset of assets in the Dagster UI automatically scopes the `sqb build` invocation to those models via `--select`.

For production deployments, use `project.prepare()` or `sqb compile --dag` to generate the DAG artifact explicitly in your CI pipeline.

### Asset selection

When you select a subset of assets in the Dagster UI, the integration automatically:

1. Maps selected Dagster asset keys back to SQLBuild model names using the DAG artifact
2. Writes the selectors to a temporary file
3. Passes `--select-file` to the `sqb` CLI so only the selected models are built

This means Dagster's asset subsetting works naturally with SQLBuild's selector system.

### Checks

SQLBuild tests, audits, and scenarios are registered as Dagster asset checks:

- **Unit tests** become checks attached to the models they test
- **Audits** become checks attached to the model or source they audit, with severity mapped to `AssetCheckSeverity.ERROR` or `AssetCheckSeverity.WARN`
- **Scenarios** become checks attached to the models they exercise

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

## dlt

Source: `integrations/dlt.mdx`

Use dlt pipelines inside SQLBuild source loaders.

[dlt](https://dlthub.com) is an open-source Python library for loading data from APIs, databases, cloud storage, and other sources. You can use dlt inside a SQLBuild [source loader](/concepts/loaders) to ingest data as part of your build lifecycle.

### Install

```bash
pip install 'dlt[duckdb]'
# or for Snowflake
pip install 'dlt[snowflake]'
```

Install dlt with the extras matching your SQLBuild adapter.

### How it works

A self-managed loader calls `dlt.pipeline(...).run(...)` to load data into the same database that SQLBuild manages. The loader returns `None` - dlt handles the writes, and SQLBuild treats the source as loaded.

```
loaders/               # dlt pipelines wrapped as loaders
  github_sources.py
sources/
  github.yml           # source declarations bound to loaders
models/
  staging/
    stg_issues.sql     # __source("raw_github_issues")
```

### Example: REST API source

Load GitHub issues into a source table using dlt's REST API source:

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
        "resources": [
            {
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
            },
        ],
    })

    pipeline = dlt.pipeline(
        pipeline_name="github_issues",
        destination=dlt.destinations.duckdb(ctx.connection),
        dataset_name=ctx.target_schema or "main",
    )
    pipeline.run(source)
```

Bind it to a source:

```yaml
# sources/github.yml
sources:
  - name: raw_github_issues
    loader: raw_github_issues
    table: issues
    columns:
      - name: id
        type: INTEGER
      - name: title
        type: VARCHAR
      - name: state
        type: VARCHAR
      - name: created_at
        type: TIMESTAMP
```

Reference it in models:

```sql
SELECT id, title, state FROM __source("raw_github_issues")
```

### Example: SQL database source

Replicate a table from a PostgreSQL database:

```python
# loaders/postgres_sources.py
import dlt
from dlt.sources.sql_database import sql_database
from sqlbuild.loaders import loader
from sqlbuild.executor.load.models import LoaderContext

@loader
def raw_pg_customers(ctx: LoaderContext):
    source = sql_database(
        ctx.vars["postgres_connection_string"],
        table_names=["customers"],
    )

    pipeline = dlt.pipeline(
        pipeline_name="pg_customers",
        destination=dlt.destinations.duckdb(ctx.connection),
        dataset_name=ctx.target_schema or "main",
    )
    pipeline.run(source)
```

### Passing credentials

Use SQLBuild [project variables](/concepts/project-configuration#project-variables) to pass credentials to dlt without hardcoding them:

```toml
# sqlbuild_local.toml (gitignored)
[vars]
github_token = "ghp_..."
postgres_connection_string = "postgresql://user:pass@host:5432/db"
```

Access them in the loader via `ctx.vars["github_token"]`.

For production, set variables via environment variables or per-environment config:

```toml
# sqlbuild_project.toml
[environments.prod.vars]
github_token = "${GITHUB_TOKEN}"
```

### DuckDB connection sharing

When using the DuckDB adapter, you can pass `ctx.connection` directly to dlt's DuckDB destination. This reuses SQLBuild's open connection, so dlt writes into the same database file without needing a separate connection string:

```python
pipeline = dlt.pipeline(
    pipeline_name="my_pipeline",
    destination=dlt.destinations.duckdb(ctx.connection),
    dataset_name=ctx.target_schema or "main",
)
```

### Warehouse destinations

For Snowflake, BigQuery, or Databricks, configure dlt with its own connection credentials. dlt writes directly to the warehouse, and SQLBuild reads the resulting tables as sources:

```python
@loader
def raw_api_data(ctx: LoaderContext):
    source = rest_api_source({...})

    pipeline = dlt.pipeline(
        pipeline_name="api_data",
        destination="snowflake",
        dataset_name=ctx.target_schema or "public",
    )
    pipeline.run(source)
```

Configure dlt credentials via its own `secrets.toml` or environment variables as described in the [dlt documentation](https://dlthub.com/docs/general-usage/credentials/setup).

### Build integration

Loaders run automatically during `sqb build` (when `auto_load_sources` is enabled). This means dlt pipelines execute as part of the normal build lifecycle:

```bash
# dlt loaders run, then models build
sqb build

# skip loading (use existing source data)
sqb build --no-load

# run loaders standalone
sqb load
```

See [Loaders](/concepts/loaders) for details on write strategies, the loader context API, auto-load behavior, and source deferral.

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
| `--defer-to` | Resolve unselected model references against another environment |
| `--json` | Output the full compile report as JSON |
| `--manifest` | Generate `target/manifest.json` with project metadata |
| `--lineage-mode` | Column lineage mode: `fast` (default), `rich` (slower, more detail), or `none` |

### What compile does

1. **Discovery** - finds `sqlbuild_project.toml`, scans for models, sources, seeds, functions, audits, tests, and macros
2. **Graph resolution** - resolves `ref()` and `source()` calls, expands macros, orders models by dependency
3. **SQL validation** - validates SQL syntax using SQLGlot (when enabled)
4. **Column lineage** - analyzes column-level dependencies across models (fast mode by default)
5. **Contract validation** - checks declared column contracts against inferred query output
6. **Artifact write** - writes compiled SQL to `target/compiled/`

### Static analysis

When SQLGlot is enabled (default), compile performs static analysis on your models without connecting to the warehouse:

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
| `rich` | Full SQLGlot-based analysis with transform classification and deeper tracing. Slower on large projects. |
| `none` | Skip column lineage entirely. |

Column lineage results are included in the JSON compile report under each model's `lineage` field. See [Column Lineage](/concepts/column-lineage) for details on analysis modes and transform types.

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
| `--defer-to` | Resolve unselected model references against another environment |
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

## build

Source: `cli/build.mdx`

Execute the full build lifecycle: seeds, tests, models, and audits.

## sqb build

Compiles, plans, and executes the full build lifecycle including seeds, SQL unit tests, model materialization, and audits.

### Usage

```bash
sqb --project-dir <path> build [flags]
```

### Flags

| Flag | Description |
|------|-------------|
| `--no-sql-validation` | Skip compile-time SQL syntax validation |
| `--defer-to` | Resolve unselected model references against another environment |
| `--full-refresh` | Drop and rebuild all selected models from scratch |
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
| `--defer-sources-to` | Read managed source data from another environment |
| `--select`, `-s` | Select specific models |
| `--exclude` | Exclude specific models |

### Execution order

1. Managed sources are loaded (unless `--no-load`)
2. Seeds are loaded
3. Source audits run before their dependent models
3. SQL unit tests run before their target model
4. Models are materialized in DAG topological order
5. Error-severity audits run against the staging table before promotion to the target

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

Use `--defer-to` to resolve unselected model references against another environment. This lets you build a subset of models in dev while referencing production tables for everything else:

```bash
sqb build --select fact_orders --defer-to prod
```

No `manifest.json` is required. Deferred references resolve directly against the live environment.

### Failure behavior

When a model fails:
- Downstream models are automatically blocked and skipped
- Staging/delta tables are retained for inspection
- Failure details show the model name, failed phase, and error message

### Fingerprints

After a successful build, SQLBuild writes query fingerprints to `_sqlbuild_fingerprints` in the target schema. These are used by `plan` to detect query changes on subsequent runs.

### Runtime artifacts

Build writes executed lifecycle SQL to `target/run/models/`. These files contain the actual SQL that was executed, including resolved cursor bounds and runtime substitutions.

## run

Source: `cli/run.mdx`

Execute models without tests or audits.

## sqb run

Same as `build` but skips SQL unit tests and audits. Useful for fast iteration when you only want to materialize models.

### Usage

```bash
sqb --project-dir <path> run [flags]
```

### Flags

| Flag | Description |
|------|-------------|
| `--no-sql-validation` | Skip compile-time SQL syntax validation |
| `--defer-to` | Resolve unselected model references against another environment |
| `--full-refresh` | Drop and rebuild all selected models from scratch |
| `--fail-fast` | Stop on first failure and skip remaining nodes |
| `--concurrency` | Number of worker connections (default: 1) |
| `--verbose`, `-v` | Show lifecycle SQL inline after each model |
| `--start-cursor-ts` | Override start cursor for timestamp incremental models (ISO format) |
| `--end-cursor-ts` | Override end cursor for timestamp incremental models (ISO format) |
| `--start-cursor-int` | Override start cursor for integer incremental models |
| `--end-cursor-int` | Override end cursor for integer incremental models |
| `--load` | Explicitly load managed sources before running |
| `--no-load` | Skip automatic source loading |
| `--reload` | Reload managed sources (passes `is_reload=True` to loaders) |
| `--defer-sources-to` | Read managed source data from another environment |
| `--select`, `-s` | Select specific models |
| `--exclude` | Exclude specific models |

## test

Source: `cli/test.mdx`

Run SQL unit tests in isolation.

## sqb test

Runs SQL unit tests without building models. Useful for validating test logic independently.

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
| `--defer-to` | Resolve model references against another environment |
| `--select`, `-s` | Select audits attached to specific models |
| `--exclude` | Exclude audits attached to specific models |

### Examples

```bash
# Run all audits
sqb audit

# Run audits for marts only
sqb audit --select path:marts
```

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

`sqb build` and `sqb run` automatically load managed sources before building dependent models. This is controlled by the `auto_load_sources` setting (default: `true`) and the `--load` / `--no-load` / `--reload` flags:

```bash
# Default: auto-load is on
sqb build

# Explicitly skip loading
sqb build --no-load

# Force reload
sqb build --reload
```

See [Loaders](/concepts/loaders) for full documentation on write strategies, the loader context API, and source deferral.

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

## clone

Source: `cli/clone.mdx`

Copy models between environments using zero-copy cloning.

## sqb clone

Copies model relations from one environment to another. Uses zero-copy cloning where the adapter supports it, falling back to physical copies with `--hard-copy`.

No `manifest.json` generation or artifact management is required. Clone works directly against live environments.

### Usage

```bash
sqb --project-dir <path> clone --from <env> --to <env> [flags]
```

### Flags

| Flag | Description |
|------|-------------|
| `--from` | Source environment (required) |
| `--to` | Target environment (required) |
| `--hard-copy` | Force physical table copies instead of zero-copy cloning |
| `--no-sql-validation` | Skip compile-time SQL syntax validation |
| `--select`, `-s` | Select specific models to clone |
| `--exclude` | Exclude specific models from cloning |

### Examples

```bash
# Clone all models from prod to dev
sqb clone --from prod --to dev

# Clone only marts to dev
sqb clone --from prod --to dev --select path:marts

# Force physical copies
sqb clone --from prod --to dev --hard-copy
```

### Clone policies

Environments must allow cloning in `sqlbuild_project.toml`. See [Project Configuration](/concepts/project-configuration) for details.

## diff

Source: `cli/diff.mdx`

Compare schemas and data between environments.

Compares schemas and optionally row-level data between two environments. See [Environment Diffs](/concepts/environment-diffs) for detailed usage.

### Usage

```bash
sqb diff <FROM>:<TO> <mode> [flags]
```

The first argument is a positional environment range in `FROM:TO` format. Exactly one mode is required: `--full`, `--schema-only`, or `--bounded <duration>`.

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
sqb diff prod:dev --schema-only --select path:marts

# Bounded diff of last 14 days
sqb diff prod:dev --bounded 14d --select hourly_order_activity
```

### Exit codes

Returns `0` when all selected models have no differences, `1` when any model has schema or row differences.

## lineage

Source: `cli/lineage.mdx`

Explore model and column-level dependency graphs from the command line.

Inspect upstream and downstream dependencies for any model, source, seed, or function in your project. Supports both model-level lineage (dependency graph) and column-level lineage (tracing individual columns through transformations). Outputs as a tree, edge list, or structured JSON.

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

Column lineage supports `upstream` and `downstream` directions (not `both`). The `--mode` flag selects the analysis mode: `rich` (default, full SQLGlot analysis) or `fast` (lightweight, faster on large projects).

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
sqb lineage --select path:marts

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

**Configuration** - Finds and validates `sqlbuild_project.toml`, loads `sqlbuild_local.toml` if present, resolves the adapter and active environment.

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
  environment: dev [OK resolved]

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

### Safety

Janitor prompts for confirmation before deleting. The confirmation requires typing an exact string to prevent accidental deletion. Use `--auto-approve` only in CI or when you're certain.

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

## scenario

Source: `cli/scenario.mdx`

Run end-to-end scenario tests against the warehouse or locally with DuckDB.

## sqb scenario

Run end-to-end scenario tests. Scenarios materialize fixture inputs as physical relations, build the real project graph against them, and evaluate expected outputs and assertions. See [Scenarios](/concepts/scenarios) for concepts and authoring details.

### sqb scenario test

Run scenario tests against the warehouse.

```bash
sqb scenario test [selectors...] [flags]
```

#### Flags

| Flag | Description |
|------|-------------|
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

Zero or more selectors can be provided. Without selectors, all discovered scenarios run.

| Selector | Example |
|----------|---------|
| Scenario name | `sqb scenario test daily_revenue_minimal` |
| Multiple names | `sqb scenario test daily_revenue_minimal daily_revenue_multi_order` |
| `.sql` file path | `sqb scenario test tests/scenarios/revenue/daily_revenue_minimal.sql` |
| Folder | `sqb scenario test tests/scenarios/revenue` |
| Scenario-root-relative folder | `sqb scenario test revenue` |

Mixed selector types are supported and de-duplicated by scenario name.

#### Remote examples

```bash
# Run all scenarios
sqb scenario test

# Run one scenario
sqb scenario test daily_revenue_minimal

# Run and retain warehouse artifacts
sqb scenario test daily_revenue_minimal --retain

# Run all scenarios in a folder
sqb scenario test revenue
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
sqb scenario capture [selectors...] [flags]
```

#### Flags

| Flag | Description |
|------|-------------|
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
sqb scenario capture daily_revenue_minimal

# Capture and retain warehouse artifacts
sqb scenario capture daily_revenue_minimal --retain
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

## dbt

Source: `cli/dbt.mdx`

Run SQLBuild alongside an existing dbt project.

## sqb dbt

Orchestrate dbt and SQLBuild together. Each subcommand runs dbt first, then SQLBuild, with selection logic that works across both project graphs. See [dbt Interop](/concepts/dbt-interop) for concepts and selection behavior.

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

### sqb dbt test

Run dbt tests first, then SQLBuild unit tests and audits for selected models.

```bash
sqb dbt test [--select <selector>...] [--exclude <selector>...]
```

dbt's `test_type:data` and `test_type:unit` selectors are mapped: `test_type:data` runs SQLBuild audits, `test_type:unit` runs SQLBuild unit tests. Without a test type selector, both run.

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
sqb dbt build --select path:marts

# Exclude by tag
sqb dbt build --select fact_orders+ --exclude tag:nightly
```

See [dbt Interop - Selection behavior](/concepts/dbt-interop#selection-behavior) for full details on how selectors route work between dbt and SQLBuild.

### Configuration

Configure the dbt project location in `sqlbuild_project.toml`:

```toml
[dbt]
project_dir = "../dbt_project"
profiles_dir = "../profiles"
target_path = "../dbt_project/target"
```

See [Project Configuration](/concepts/project-configuration) for details.

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

The argument is used as both the template name and the directory name. If omitted, the default `waffle_shop` template is used and the project is created in a directory matching the template name.

### Templates

| Template | Description |
|----------|-------------|
| `waffle_shop` | Default. DuckDB-backed project with models, tests, scenarios, and macros. |
| `dagster` | Waffle shop project plus a `dagster/` directory with a ready-to-run `definitions.py`. |

### What it creates

A complete DuckDB-backed project with:

- Staging views, fact/dimension tables, and incremental models
- Sources with inline expression data (no external setup)
- Seeds, SQL functions, and a custom materialization
- Built-in and custom audits
- SQL unit tests including chain tests
- E2E scenario tests
- Python macros
- AI agent skill files (auto-installed for OpenCode, Claude Code, and other agents)

The `dagster` template adds:

- `dagster/definitions.py` - Dagster definitions with `sqlbuild_assets`, `sqlbuild_scenario_checks`, and `SqlBuildCliResource`
- `dagster/README.md` - Setup instructions

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
```

### Notes

- The target directory must not already exist
- DuckDB is included as a core dependency - no extra installation needed
- The local DuckDB database file is created on the first build
- The Dagster template uses `prepare_if_dev()` to auto-generate the DAG artifact when Dagster starts in dev mode
