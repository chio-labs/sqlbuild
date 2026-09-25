---
name: sqlbuild
description: ALWAYS load this skill when doing ANY SQLBuild work - models, sources, seeds, macros, enums, constants, tests, audits, scenarios, incremental and microbatch models, configuration, CLI, adapters, or dbt interop. Covers the verify loop (compile, plan, build), comparing data or two queries with sqb diff, inspecting macro/enum/constant visibility with sqb scope, impact analysis with sqb lineage, and where to find exact syntax.
---

# SQLBuild

SQLBuild builds SQL and Python data pipelines. It looks like dbt (SQL models, refs, sources, seeds,
selectors) but compiles and checks the whole project offline first, explains every build with a
plan, and ships tools for proving a change is correct. Use those tools; do not stop at "it ran".

## How SQLBuild differs from dbt

- Models are SQL files with a `MODEL (...)` header, then one query. No Jinja.
- References are `__ref("model")`, `__source("source_name")`, `__seed("seed")`. Never hardcode a
  relation SQLBuild manages.
- Macros are plain Python functions called as `@macro_name("arg")`. Constants and enums are
  `@const("name")` and `@enum("name").MEMBER`.
- Config, column schemas, contracts and audits live in the `MODEL()` header, not YAML.
- `sqb compile` is offline: syntax, per-input binding, grouping semantics, contracts, metadata,
  column lineage and Rules run before warehouse execution. Explicit projections close output names
  even over open inputs. General expression type checks await the dialect coercion catalogue.
  Open table sources need an enforced contract or plan/build warehouse inspection for complete
  column checking. `--json` reports partial-check reasons. Intentional escape hatches are
  `MODEL (sql_analysis false)`, path defaults, and `--no-sql-analysis` (also disabling inference
  and lineage).
- Declarations are scoped by folder. A macro, enum or constant must live in the narrowest folder
  that contains every use, or compile rejects it. See `sqb scope` below.
- Plans record why each model runs (first run, query change, config change, upstream change).
- Destructive changes are gated: snapshot full refreshes, permanent-to-transient table changes and
  time travel retention decreases need an explicit policy or flag. Never pass an `--allow-*`
  flag without the user's say-so.

```sql
-- models/marts/fact_orders.sql
MODEL (
  materialized table,
  columns (
    order_id (audits [not_null, unique]),
  ),
);

SELECT o.order_id, o.customer_id, p.amount_cents AS total_cents
FROM __ref("stg_orders") o
JOIN __ref("stg_payments") p USING (order_id)
```

## The working loop

1. **Orient.** Read `sqlbuild_project.toml` (and `sqlbuild_local.toml` if present) and look at
   neighbouring models to match layout, naming and style. Use `sqb lineage` and `sqb scope` rather
   than guessing how pieces connect.
2. **Look at the data.** `sqb query "SELECT ..." --limit 20` runs SQL on the active target. Profile
   inputs (counts, nulls, key uniqueness) before writing joins.
3. **Compile.** `sqb compile --select <models>` after every edit. It is offline and fast.
4. **Plan.** `sqb plan --select <models>` shows exactly what a build will do and why. Read it before
   building, especially for incremental models, full refreshes and anything destructive.
5. **Test.** `sqb test --select <models>` runs SQL unit tests without building.
6. **Build.** `sqb build --select <models>` runs tests, builds, and runs audits in DAG order.
   Use `--defer-to <target>` to read unselected upstream models from another target instead of
   rebuilding them.
7. **Verify.** Prove the result is right with `sqb diff` (below), not only that it built.

When something fails, run `sqb debug` first. It separates configuration, authentication and
connection problems from command-specific errors. `sqb debug --no-connection` checks config only.

## Reach for these tools

These are SQLBuild's highest-leverage features and the ones most often missed. Use them whenever
the trigger applies.

| When you need to... | Use |
|---|---|
| Check a refactor did not change results, or compare dev with prod | `sqb diff prod:dev --full --select <model>` |
| Compare two arbitrary queries (old vs new logic, before vs after a fix, two tables) | `sqb diff --left-query "..." --right-query "..." --key <col>` |
| Know what a model can see: which macros, enums and constants are visible, used, or unavailable | `sqb scope model:<name>` |
| Fix "unknown macro/enum/constant", or decide where a declaration should live | `sqb scope model:<name> --explain macro:<name>` |
| Preview whether moving a file breaks declaration visibility | `sqb scope model:<name> --as-path <new/path.sql>` |
| Find what a model depends on, or what breaks if it changes | `sqb lineage <model> --direction both` |
| Trace where a column comes from, or who consumes it before renaming or dropping it | `sqb lineage <model>.<column> --direction downstream` |
| See which intermediate models a SQL test will really execute | `sqb test --select <model> --inspect` |
| Inspect the full graph as data | `sqb dag --json`, `sqb plan --json`, `sqb compile --json` |
| Adopt an existing warehouse table's columns into a contract | `sqb contract generate --from <target> --select <model>` |
| Try syntax safely in a throwaway DuckDB project | `sqb playground /tmp/sqb-sandbox` |

### Data diff and query diff

`sqb diff` is the main verification tool. Use it after any logic change.

```bash
# Model diff between two targets; needs FROM:TO, --select and exactly one mode.
# --full and --bounded need the model's unique_key.
sqb diff prod:dev --full --select fact_orders
sqb diff prod:dev --schema-only --select path:models/marts
sqb diff prod:dev --bounded 14d --select hourly_order_activity

# Query diff: compare any two queries on the active target (or --target).
sqb diff \
  --left-query "SELECT order_id, total_cents FROM analytics.fact_orders" \
  --right-query-file /tmp/new_fact_orders.sql \
  --key order_id --left-label current --right-label proposed
```

Query diff requires `--key` (repeat it for composite keys) or `--unkeyed` for exact row-multiset
comparison. Queries are raw warehouse SQL: use physical relation names, not `__ref()`. Exit codes:
`0` identical, `1` differences, `2` incomplete or error. Read
[references/verifying-changes.md](references/verifying-changes.md) for tolerances, excluded
columns, type mismatches and JSON output.

## Must-know behaviour by area

**Incremental models.** Cursor-based (`cursor`, `cursor_type`, `cursor_grain`, `cursor_inputs`).
SQLBuild computes the replay window and automatically filters every input listed in
`cursor_inputs` to that window (in watermark microbatch models, inputs with the `filter` role), so
do not hand-write that filter. Unlisted inputs are read in full. Use `__cursor_start()` /
`__cursor_end()` only when SQL needs the bounds explicitly. Microbatch mode
(`incremental_mode microbatch` with `microbatch_strategy watermark` or `rolling_window`) splits the
window into batches, each with its own audits. Always `sqb plan` an incremental change before building. Read
[references/incremental-models.md](references/incremental-models.md).

**Tests.** SQL unit tests live under `tests/unit/`. A `TEST();` file mocks inputs with
`__source__<name>`, `__ref__<name>`, `__seed__<name>` CTEs, states expected output with
`__expected__<model>` (only the listed columns are compared, matched by name; unlisted columns are
ignored), adds zero-row checks with `__assert__<name>`, and ends with `SELECT 1`.
One test can span many models: mock the sources, assert on the final model, and every intermediate
model runs from its real SQL. Never write a test that only proves empty inputs produce no rows; it
cannot fail, Rules reject it, and it does not count toward `min_tests_per_model`. Mock real rows
and assert concrete output. Read [references/testing.md](references/testing.md) for fixtures,
parameterised cases, scenarios, audits and Rules.

**Audits** validate built data and block bad data: `error` audits run on staging data before the
swap for tables, and on each delta before DML for incremental models. Attach built-ins such as
`not_null` and `unique` in the column schema.

**Macros, enums and constants.** Macros are Python functions returning SQL strings; arguments are
Python literals, and SQL expressions are passed as quoted strings. Public functions become macros;
prefix helpers with `_`. Macros work in model SQL, SQL hooks, tests, scenarios, audits and SQL
functions, but not in ordinary `MODEL()` config fields. Placement decides visibility. Read
[references/macros-and-declarations.md](references/macros-and-declarations.md).

**Snapshots** (SCD type 2) use `timestamp` or `check` strategies; full refreshes are policy-gated.

**Rules** are compile-time project checks (`sqb rules list`, `sqb rules show <code>`). `sqb format`
rewrites sources deterministically; `sqb format --check` only reports.

**dbt projects.** `sqb dbt plan|run|build --select ...` drives dbt for dbt-owned models and runs
SQLBuild models downstream of them.

## Selectors

`--select a b` unions, `--exclude` subtracts. `+model` includes upstream, `model+` downstream.
`tag:<tag>`, `path:models/marts` (or any value containing `/`), `seed:<name>`, `source:<name>`,
and quoted name globs such as `"stg_*"`. They work with plan, build, test, audit, seed, clone and
diff.

## Exact syntax and everything else

- Task guides, one level deep:
  - [references/verifying-changes.md](references/verifying-changes.md): data diff and query diff.
  - [references/exploring-a-project.md](references/exploring-a-project.md): scope, lineage, dag,
    query, plan and compile output.
  - [references/incremental-models.md](references/incremental-models.md): strategies, cursors,
    microbatch, watermarks, limits, replay.
  - [references/testing.md](references/testing.md): unit tests, fixtures, scenarios, audits,
    Rules.
  - [references/macros-and-declarations.md](references/macros-and-declarations.md): macros,
    enums, constants, placement and scopes.
- Full documentation for this SQLBuild version: [references/docs/CONTENTS.md](references/docs/CONTENTS.md)
  lists every page; open only the page you need, for example `references/docs/cli/build.md` or
  `references/docs/concepts/snapshots.md`. The same pages are online at
  https://docs.sqlbuild.com if you need a newer version.
