# DuckShop runbook

How to load DuckShop's synthetic data into Snowflake, build and test the project, capture the
scenario snapshots, and clean up afterwards. Run every command from `benchmarks/duckshop/project`
unless it says otherwise.

## 1. Configure the connection

Install SQLBuild with Snowflake support (`pip install "sqlbuild[snowflake]"`), then create the
untracked local configuration:

```bash
cd benchmarks/duckshop/project
cp sqlbuild_local.toml.example sqlbuild_local.toml
```

Fill in the account, user, authenticator, role and warehouse, and the `database` and `schema` of
`[targets.dev]`. Keep the project's `session_parameters` setting on the connection (see Known
limitations in the README): `sqlbuild_local.toml` adds to the `[connections.warehouse]` table in
`sqlbuild_project.toml` rather than replacing it, so leave `session_parameters` out of the local
file. `sqlbuild_local.toml` is gitignored; never commit it, and never copy its values
into tracked files, commit messages or pull requests.

Check the connection, then confirm the project compiles:

```bash
sqb debug
sqb compile
```

`sqb compile` must report `0 errors, 0 warnings`.

## 2. Check the schema before the first build

A build creates or replaces about 340 objects in the target schema: 252 models, 5 seeds, 76 raw
source tables and 3 functions. If the schema holds other work, make sure none of it has a DuckShop
name:

```bash
sqb compile --json > target/duckshop-compile.json
python ../scripts/relations.py check target/duckshop-compile.json > target/check.sql
sqb query --file target/check.sql --no-limit
```

The query lists every existing table, view or function with a DuckShop name, which is everything
step 7 drops, and any SQLBuild state tables (`_SQLBUILD_*`). Before the first build it should list
no DuckShop names; if it does, stop and pick another schema. Note which state tables already existed, for the cleanup in step 7.

## 3. Load the synthetic data

```bash
sqb load --concurrency 4
```

All 76 managed sources load, about 60,000 rows in total. Each loader replaces its table, so loading
again gives identical data. The volume multiplier is the `data_scale` project variable; for a larger
run, set it in `sqlbuild_local.toml`:

```toml
[vars]
data_scale = "10"
```

## 4. Build

```bash
sqb build --concurrency 8
```

The build reloads the managed sources first. SQLBuild 0.175.0 does this even with `--no-load`
when no `--select` is given, because the default selection includes the sources themselves; the
reload writes the same rows as step 3, so it only costs time. The first build replays the
clickstream microbatch models from the start of their history, about 90 six-hour batches, so it
takes longer than later builds.

Audits run during the build. Error-severity failures stop the dependent models and fail the
command. A few warn-severity audits, such as `orders_balance_to_payments` (orders part-paid with
gift cards) and the buyer match rate on partner orders, may report findings without failing.

### Rebuilding after a model change

Incremental models are forward-only by default: when a model's SQL changes, rows already built keep
their old results and only new cursor ranges use the new query, and the plan prints a warning that
says so. Each model's `replay_on_change` setting decides how much history its own change
reprocesses. Upstream changes never replay a downstream model.

DuckShop's history is small and fixed (January to March 2026 at every `data_scale`), so its
incremental models replay all of it when they change:

| Model | Policy |
|-------|--------|
| `stg_web_events`, `int_web_sessions` (microbatch) | `replay_on_change full` |
| `fct_web_sessions`, `fct_support_tickets`, `fct_inventory_daily` | `replay_on_change bounded-120d`, which covers all synthetic history |
| `stg_app_events` (append) | forward-only; replaying an append model would duplicate rows |

`full` is not used for the three non-microbatch models because a full rebuild of a model that
filters on `__cursor_start()` needs an explicit interval. To reprocess a model by hand, for example
after an upstream change or for `stg_app_events`:

```bash
# Microbatch models
sqb build --select stg_web_events --full-refresh
# Models that filter on cursor intrinsics without microbatches: give the interval explicitly
sqb build --select fct_web_sessions --full-refresh \
  --start-cursor-ts 2026-03-01T00:00:00 --end-cursor-ts 2026-04-02T00:00:00
```

## 5. Run the unit tests and scenarios on Snowflake

```bash
sqb test --concurrency 8
sqb scenario test --concurrency 4
```

Unit tests and scenarios read only their own fixtures, not the loaded data, so they can run before
or after the build. Their expected values were derived by hand; all 266 tests and 8 scenarios pass
on Snowflake. Report any failure rather than editing the expectations to match.

## 6. Capture the scenario snapshots and commit them

```bash
sqb scenario capture
sqb scenario test --local --strict
```

Capture materialises each scenario's fixtures in Snowflake, downloads them as JSONL into
`tests/_scenario_snapshots/`, and drops what it created. The local run then replays all 8
scenarios on your machine from those files, with no warehouse connection; `--strict` fails on a
missing or stale snapshot instead of skipping it.

With SQLBuild 0.175.0 the local run is expected to end with `ERROR=8`: five scenarios fail while
translating Snowflake SQL to DuckDB, and three report `X602` (stale snapshot) because of a
SQLBuild fingerprint issue. Both are described in the README's status section. Capturing again does
not clear the `X602` errors.

The snapshots hold only the synthetic fixture rows and column types, but check them before
committing. From the repository root:

```bash
grep -ril "<your schema>\|<your account>" benchmarks/duckshop/project/tests/_scenario_snapshots
git add benchmarks/duckshop/project/tests/_scenario_snapshots
git commit -m "test(benchmarks): capture DuckShop scenario snapshots"
```

The `grep` must print nothing. The repository's publication checks run on commit and push as usual.

## 7. Clean up

Drop everything the project created, by name:

```bash
sqb compile --json > target/duckshop-compile.json
python ../scripts/relations.py drop target/duckshop-compile.json > target/drop.sql
sqb query --file target/drop.sql
sqb clean
```

`drop.sql` is one Snowflake Scripting block of `DROP ... IF EXISTS` statements for every model,
snapshot, seed, raw source table and function, so it is safe to run twice. Scenario runs and
captures already drop their own relations.

SQLBuild also keeps state tables (`_SQLBUILD_*`) in the schema. If step 2 showed none before the
first build, they belong to DuckShop alone and you can drop them too. List them, then drop each
one by name:

```bash
sqb query "SHOW TABLES LIKE '\\_SQLBUILD\\_%'"
sqb query "DROP TABLE IF EXISTS <name>"
```

`sqb janitor` is not used here. It archives relations the current project no longer produces and
keeps the ones it does, so it would leave DuckShop's own tables in place. In a schema that other
SQLBuild projects also write to, it could archive their relations instead.
