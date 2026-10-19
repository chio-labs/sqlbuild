<!-- generated-by: sqlbuild skills -->

# DuckDB

> DuckDB adapter configuration for SQLBuild.

Online: https://sqlbuild.com/docs/concepts/adapters/duckdb/

DuckDB is included as a core dependency. No extra installation needed.

## Connection config

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

## Extensions and settings

```toml
[connections.local]
database = "my_project.duckdb"
extensions = ["httpfs", "parquet"]

[connections.local.settings]
memory_limit = "4GB"
```

## Attaching additional databases

```toml
[connections.local]
database = "my_project.duckdb"

[[connections.local.attach]]
path = "external_data.duckdb"
alias = "external"
read_only = true
```

## Table promotion mode

DuckDB defaults to `staged` promotion: tables are materialized into a staging table, audited, then swapped into the target. This is configurable in `settings`:

```toml
[settings]
table_promotion_mode = "staged"
```

## Functions in unit tests

`sqb test` copies each SQL UDF and table function the selected tests call into a `CREATE TEMP
MACRO` on every test connection, called as `temp.main.<name>`, so tests use the current project
definition without a build. Python UDFs are registered on each test connection. See [Functions in `sqb test`](../testing.md#functions-in-sqb-test).
