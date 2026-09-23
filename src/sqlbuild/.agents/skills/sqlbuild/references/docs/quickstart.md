<!-- generated-by: sqlbuild skills -->

# Quickstart

> Get a SQLBuild project running locally with DuckDB in under a minute.

Online: https://docs.sqlbuild.com/quickstart

## Contents

- Prerequisites
- 1. Create the playground
- 2. Plan
- 3. Build
- 4. Verify
- 5. Common operations
- What you just built
- Next steps

This guide walks you through creating and running a complete transformation project - views, tables, incremental models, audits, tests, and a custom materialization - all running locally against DuckDB. No external data setup or warehouse credentials required.

## Prerequisites

- Python 3.12+
- SQLBuild installed: `uv pip install sqlbuild` or `pip install sqlbuild`

Confirm the installed release with `sqb --version`.

## 1. Create the playground

```bash
sqb playground waffle-shop
cd waffle-shop
```

This creates a self-contained waffle shop project with everything you need to explore SQLBuild.

The playground creates the shared `sqlbuild_project.toml`; that is sufficient for this
quickstart. In a team project, you can additionally create a gitignored
`sqlbuild_local.toml` to select your usual target and override your personal development
schema or credentials without changing the committed project config. See
[Project Configuration](concepts/project-configuration.md#sqlbuild_local-toml).

## 2. Plan

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

## 3. Build

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

## 4. Verify

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

## 5. Common operations

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

## What you just built

### Model DAG

```
raw__customers ──> stg_customers ──> dim_customers
raw__orders ────> stg_orders ────> fact_orders ──> customer_status_snapshot
raw__payments ──> stg_payments ──>  │              order_status_index
                                   │              hourly_order_activity ──> daily_activity_rollup
                                   │                                       hourly_activity_with_daily_context
                                   └──> daily_revenue
                                   └──> daily_order_partitioned
```

### Materialization types

The project demonstrates several materialization strategies:

- **Views** (`stg_customers`, `stg_orders`, `stg_payments`) - lightweight staging layer
- **Tables** (`fact_orders`, `dim_customers`, `daily_revenue`) - full table rebuilds
- **Merge incremental** (`customer_status_snapshot`) - upsert with timestamp cursor
- **Delete/insert incremental** (`hourly_order_activity`, `daily_activity_rollup`, `hourly_activity_with_daily_context`) - microbatch processing with configurable batch sizes
- **Integer cursor incremental** (`order_status_index`) - non-timestamp incremental
- **Custom materialization** (`daily_order_partitioned`) - Python-defined partition-tracked strategy

See [Incremental](concepts/incremental.md) for details on cursor-based strategies and microbatch processing.

### Project structure

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

## Next steps

- [Models](concepts/models.md) - understand `MODEL()` headers and materialization types
- [Rules](concepts/rules.md) - add compile-time SQL, architecture, and model-shape checks
- [Functions](concepts/functions.md) - SQL UDFs, Python UDFs, and table functions
- [Incremental](concepts/incremental.md) - learn about cursor-based incremental strategies
- [Audits](concepts/audits.md) - configure data quality checks
- [Testing](concepts/testing.md) - write SQL unit tests and multi-model tests with macro support
- [Column Lineage](concepts/column-lineage.md) - trace individual columns through your pipeline
- [CLI Reference](cli/build.md) - full command reference
