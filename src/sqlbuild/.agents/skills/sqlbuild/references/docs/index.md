<!-- generated-by: sqlbuild skills -->

# Introduction

> The refactorable warehouse. Verify early, test properly, and refactor safely.

Online: https://sqlbuild.com/docs/

SQLBuild is a free, open-source framework for SQL and Python data pipelines. It brings compile-time
checks, tests and diffs to your warehouse, so you can change it as often as you change your code.

Valid SQL isn't the same as correct SQL. A query can compile, run and return rows, and still produce
a wrong number that people already trust. SQLBuild is built to catch that before it reaches
production.

## Verify early

Before anything runs, `sqb compile` analyses the whole project offline, with no warehouse
connection. It checks SQL, model references and declared [contracts](concepts/models/contracts.md),
and traces [column lineage](concepts/column-lineage.md). [Rules](concepts/rules.md) turn
decisions from code review into compile errors, and
[declaration scopes](concepts/declaration-scopes.md) keep enums, constants and macros visible only
where they are used.

## Test properly

[SQL unit tests](concepts/testing.md) mock your sources, resolve every model in between from its
real SQL, and compare the output with what you expect. [Scenarios](concepts/scenarios.md) build the
real model graph against test data, then replay it locally on DuckDB in CI.
[Audits](concepts/audits.md) check each build before it replaces production.

## Refactor safely

[`sqb plan`](concepts/planning.md) shows why each model will run and how much it will rebuild.
[`sqb diff`](concepts/diff.md) compares real data between targets before a change ships. When you
rename a model, a [migration](concepts/models/migrations.md) moves its table instead of rebuilding
its history, and the [janitor](cli/janitor.md) archives tables the project no longer builds before
it deletes them.

## How it fits together

| Step | Command | What it does |
|------|---------|--------------|
| Compile | [`sqb compile`](cli/compile.md) | Checks the project offline |
| Test | [`sqb test`](cli/test.md) | Runs SQL unit tests |
| Plan | [`sqb plan`](cli/plan.md) | Shows what will run, why, and how much it will rebuild |
| Build | [`sqb build`](cli/build.md) | Runs tests, builds models in dependency order, and blocks bad data with audits |
| Compare | [`sqb diff`](cli/diff.md) | Compares schemas and rows between two targets |

SQLBuild works with DuckDB, MotherDuck, Snowflake, BigQuery, Databricks, PostgreSQL and SQL Server.
DuckDB runs locally, so you can try everything without warehouse credentials. See
[Adapters](concepts/adapters.md) for connection setup.

## Where to start

    Build a complete example project locally in a minute.
    Run SQLBuild alongside an existing dbt project.
    Models, tests, audits, planning and the rest.
    Every command and flag.
