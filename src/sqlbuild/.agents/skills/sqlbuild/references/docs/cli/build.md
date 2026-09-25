<!-- generated-by: sqlbuild skills -->

# build

> Compile, plan, and execute the selected build lifecycle.

Online: https://docs.sqlbuild.com/cli/build

## Contents

- Usage
- Flags
- Fast iteration
- Execution order
- Output
- Deferred builds
- Failure behavior
- Fingerprints
- Runtime artifacts

# sqb build

Compiles, plans, and executes the selected build lifecycle, running the full selected scope. Use
`--no-tests` and `--no-audits` to skip validation for fast iteration.

## Usage

```bash
sqb --project-dir <path> build [flags]
```

## Flags

| Flag | Description |
|------|-------------|
| `--target` | Build against a configured target instead of the active/default target |
| `--no-tests` | Skip SQL unit tests |
| `--no-audits` | Skip audits |
| `--no-python` | Skip read-side Python tasks and assets (loader-side Python still runs for selected sources) |
| `--no-sql-analysis` | Disable compile-time SQL analysis (`--no-sql-validation` is an alias) |
| `--no-cache` | Bypass the reusable compile-analysis cache for this invocation |
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

## Fast iteration

Use `--no-tests` and `--no-audits` to skip validation when you only want to materialize models:

```bash
sqb build --no-tests --no-audits
```

This replaces the former `sqb run` command. The full lifecycle (tests + audits) is always the default; skip flags opt out of specific phases when you need speed.

## Execution order

1. Managed sources are loaded (unless `--no-load`)
2. Seeds are loaded (if changed)
3. Source audits run before their dependent models (unless `--no-audits`)
4. SQL unit tests run before their target model (unless `--no-tests`)
5. Models are materialized in DAG topological order
6. Error-severity audits run against the staging table before promotion to the target (unless `--no-audits`)

## Output

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

## Deferred builds

Use `--defer-to` to resolve unselected model references against another target. This lets you build a subset of models in dev while referencing production tables for everything else:

```bash
sqb build --select fact_orders --defer-to prod
```

No `manifest.json` is required. `--defer-to` selects only the namespace used for unselected
references. SQLBuild resolves those relations through the active target's sole physical
connection and never opens the deferred target's connection. The deferred namespace must be
visible and readable through the active connection; deferral is not a cross-account,
cross-server, or cross-file transfer mechanism.

## Failure behavior

When a model fails:
- Downstream models are automatically blocked and skipped
- Staging/delta tables are retained for inspection
- Failure details show the model name, failed phase, and error message

## Fingerprints

After a successful build, SQLBuild writes version identities to `_sqlbuild_fingerprints` in the target schema. These are used on subsequent runs to detect changes and skip unchanged work. See [Planning and Change Detection](../concepts/planning.md) for details.

## Runtime artifacts

Build writes executed lifecycle SQL to `target/run/models/`. These files contain the actual SQL that was executed, including resolved cursor bounds and runtime substitutions.
