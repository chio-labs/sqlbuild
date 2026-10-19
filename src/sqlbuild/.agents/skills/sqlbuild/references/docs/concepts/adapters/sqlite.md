<!-- generated-by: sqlbuild skills -->

# SQLite

> SQLite adapter configuration, capabilities and limits for SQLBuild.

Online: https://sqlbuild.com/docs/concepts/adapters/sqlite/

SQLite uses the `sqlite3` module that ships with Python. No extra installation is needed.
SQLBuild requires SQLite 3.44 or newer; Python builds installed by `uv` bundle a recent version.

## Connection config

```toml
adapter = "sqlite"
default_target = "dev"

[connections.local]
path = "warehouse.sqlite"

[targets.dev]
connection = "local"
schema = "analytics"
```

| Field | Description |
|-------|-------------|
| `path` | Path to the database file, relative to the project directory. Use `:memory:` for an in-memory database. The file and its parent directory are created when missing. |
| `busy_timeout` | Seconds a writer waits for another process to release the file before failing. Default `5`. |
| `read_only` | Open the file read-only. Default `false`. |

On connect SQLBuild turns on write-ahead logging (`journal_mode=WAL`), sets the busy timeout,
enables foreign keys and sets `legacy_alter_table=ON` so that renames keep views bound by name.
WAL needs a local filesystem; do not put the file on a network share.

## Schemas

A SQLite connection is one file. SQLBuild stores each schema's relations in that file under
`<schema>__<name>`; the `main` schema keeps bare names. For example, model `orders` in schema
`analytics` is the table `analytics__orders`. Schemas are recorded in `_sqlbuild_schemas`, which
decides how such names split back into schema and relation.

- Targets and models must not set a `database`.
- Schema names cannot contain `__` or end with `_`.
- Attached databases are not used, because a SQLite view cannot reference another attached file.

## Concurrency

Readers run alongside one writer. Within one `sqb` process, writers to the same file queue for
each other, so a long model build does not make others time out. A writer in another process waits
up to `busy_timeout` and then fails with error `A702`, naming the file. Every write that spans
statements, such as a promotion, a merge or a seed load, runs in one `BEGIN IMMEDIATE` transaction
and is all or nothing.

## Types

SQLite stores values by type affinity, so SQLBuild keeps column types explicitly:

- Tables are created with explicit column definitions. A column copied from another relation keeps
  its declared type; a computed column gets the type SQLBuild infers at compile time.
- Timestamps and dates are ISO-8601 text. `CAST(x AS TIMESTAMP)` and `CAST(x AS DATE)` do not
  produce timestamps in SQLite (they keep only the leading number), so write timestamps as text
  literals or use SQLite date functions.
- Booleans are stored as `0` and `1`.
- JSON, arrays and objects are stored as JSON text.
- A column declared `DECIMAL(p, s)` or `NUMERIC(p, s)` in an enforced contract is stored as
  canonical fixed-scale text (for example `12.50`), declared `TEXT DECIMAL(p,s)`, and reported as
  `DECIMAL(p,s)`. Elsewhere decimals are stored as SQLite numbers, which are binary floating point
  above 15 significant digits.

## Capabilities

| Feature | Support |
|---------|---------|
| Tables, views, seeds, unit tests, audits | Supported |
| Incremental `append`, `merge`, `delete_insert`, cursor windows | Supported, each in one transaction |
| Microbatch | Sequential batches; `batch_concurrency` greater than 1 is refused |
| Snapshots (timestamp, check, historical) | Supported |
| Schema changes | Add, drop and rename columns in place; type changes rebuild the table in one transaction |
| `sqb diff`, `sqb clone` | Supported; clones are physical copies |
| Scenarios, `sqb scenario capture`, `--local` replay | Supported; see below |
| Statement time limits | Connection interrupt |

## Scenarios

Scenario fixtures and models are tables in the same file, named
`<schema>____sqb_<run>__<kind>__<name>`, and are dropped when the scenario finishes unless you
pass `--retain`. Concurrent scenarios queue for the file's single writer.

`sqb scenario test --local` transpiles SQLite SQL to DuckDB. Date functions with modifiers, such
as `datetime(ordered_at, 'start of day')`, have no DuckDB translation and fail locally; use
`date(...)` or `strftime(...)` in models you want to replay locally.

## Limits

| Limit | Error |
|-------|-------|
| SQL functions and table functions: SQLite has no `CREATE FUNCTION` | `A705` |
| Grants: SQLite has no privileges; grant settings are ignored | none |
| A `database` on a target or model | `A703` |
| Unknown connection keys | `A703` |
| Ambiguous schema names (`__`, trailing `_`) | `A704` |
| SQLite older than 3.44 | `A701` |
| Another process holds the write lock beyond `busy_timeout` | `A702` |
| Concurrent microbatch writes: one file has one writer | refused at plan time |
