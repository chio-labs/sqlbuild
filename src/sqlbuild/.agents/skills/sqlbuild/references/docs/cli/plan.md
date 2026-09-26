<!-- generated-by: sqlbuild skills -->

# sqb plan

> Preview what SQLBuild will do before executing.

Online: https://sqlbuild.com/docs/cli/plan/

Shows the execution plan without making any changes. Useful for inspecting change detection, backfill policies, and selector scope before building.

## Usage

```bash
sqb --project-dir <path> plan [flags]
```

## Flags

| Flag | Description |
|------|-------------|
| `--no-sql-analysis` | Disable compile-time SQL analysis (`--no-sql-validation` is an alias) |
| `--no-cache` | Bypass the reusable compile-analysis cache for this invocation |
| `--no-python` | Exclude read-side Python tasks and assets from the plan |
| `--defer-to` | Resolve unselected model references against another target |
| `--as` | Compile for another target and show its plan, including [model migration](../concepts/models/migrations.md) decisions, using the current connection. Inspection only. |
| `--json` | Output the plan as JSON |
| `--full-refresh` | Plan a full rebuild for selected models unless a model sets `full_refresh false`; `full_refresh true` forces a model without this flag |
| `--start-cursor-ts` | Override start cursor for timestamp incremental models (ISO format) |
| `--end-cursor-ts` | Override end cursor for timestamp incremental models (ISO format) |
| `--start-cursor-int` | Override start cursor for integer incremental models |
| `--end-cursor-int` | Override end cursor for integer incremental models |
| `--select`, `-s` | Select specific models |
| `--exclude` | Exclude specific models |

## Output

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

## Missing upstream dependencies

Planning a scoped selection whose upstream inputs were never built in the target fails with `S301` rather than producing a plan that would break at build time:

```
error[S301]: cannot build selected scope: 3 missing upstream dependencies (stg_orders, stg_payments, waffle_types)
```

Build the upstream chain first, or select it along with the model: `sqb build --select +fact_orders`.
