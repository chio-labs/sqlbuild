<!-- generated-by: sqlbuild skills -->

# Upgrading

> Changes that need action when you upgrade a project.

Online: https://sqlbuild.com/docs/upgrading/

## Direct mode only

SQLBuild projects run only in direct mode. Virtual environments have been removed.

Remove the following project and local configuration keys: `settings.virtual_environments`
(including `false`), `settings.changes_only`, `targets.<name>.changes_only`,
`targets.<name>.state`, and `janitor.max_checkpoints`. These keys produce explicit removal errors,
as does `run_despite_unchanged` in MODEL headers, project defaults and path defaults. Custom
materializations defining `prepare_version` also fail to load.

The `promote`, `rollback`, `reconcile`, and `state` commands, the virtual playground template,
and the `--virtual-env`, `--include-stale-upstreams`, `--changes-only`, `--allow-partial-diff` and
`clone --skip-locked` flags are no longer recognized. Direct freshness `--state`, clone, diff, and
janitor remain available. Use a separate target schema for branch trials.

### Concurrent microbatch state

Concurrent microbatch event IDs changed. Drop existing `_sqlbuild_microbatches` tables written by
earlier versions before the next concurrent run. SQLBuild creates the current table schema when
concurrent execution next needs it. Sequential runs never read or write this table.

## Implicit type conversions are errors

On DuckDB, MotherDuck, PostgreSQL, Snowflake and BigQuery, `sqb compile` now rejects implicit
conversions that the warehouse would accept but that can fail or match unintended rows depending on
the data, for example comparing an INTEGER column with a VARCHAR column. Type conflicts through
`SELECT *` are checked in every query. Each finding is a blocking error with the code of the
incompatibility it risks (B211–B218, or B301 for declared UDF arguments); see
[semantic compilation](concepts/semantic-compilation.md#diagnostic-codes).

Fix each one by writing the conversion explicitly, for example
`order_id = CAST(customer_code AS INTEGER)`, or an explicit comparison such as `quantity <> 0`.
There is no per-model suppression.
