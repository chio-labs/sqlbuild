<!-- generated-by: sqlbuild skills -->

# DuckDB

> DuckDB adapter configuration for SQLBuild.

Online: https://sqlbuild.com/docs/concepts/adapters/duckdb/

DuckDB is included as a core dependency. No extra installation needed.

SQLBuild requires DuckDB 2.0 or later. DuckDB 2.0 writes new database files in a storage format
that DuckDB 1.x cannot open, so a database file SQLBuild creates can only be read by DuckDB 2.0
clients. A file that already exists keeps its storage version, so a file created by DuckDB 1.x
stays readable by 1.x. To create a new file that 1.x can read, create it before the first build
with an explicit storage version, for example
`duckdb my_project.duckdb -storage-version v1.5.0 -c "SELECT 1"`.

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

A relative `path` of a DuckDB or SQLite file is relative to the project directory, like `database`,
and a path starting with `~/` is relative to your home directory. This also applies to `attach`
entries that come from a dbt profile: they resolve from the SQLBuild project directory, not from
the dbt project or the working directory.
Every connection of a command attaches it once: connections to the same project database share the
attachment.

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
