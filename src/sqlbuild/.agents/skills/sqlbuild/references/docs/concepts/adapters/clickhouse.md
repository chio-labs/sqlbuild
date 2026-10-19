<!-- generated-by: sqlbuild skills -->

# ClickHouse

> ClickHouse adapter configuration for SQLBuild.

Online: https://sqlbuild.com/docs/concepts/adapters/clickhouse/

## Contents

- Connection config
- Schemas are databases
- How SQLBuild writes
- Physical layout
- Reading ReplacingMergeTree sources
- Functions
- Clones
- Settings SQLBuild pins
- Limits

The ClickHouse adapter is in beta and supports a single server. Clusters (`ON CLUSTER`, replicated and distributed tables) are not supported yet. Please [report issues](https://github.com/chio-labs/sqlbuild/issues).

ClickHouse requires the optional `clickhouse-connect` dependency:

```bash
pip install 'sqlbuild[clickhouse]'
# or
uv pip install 'sqlbuild[clickhouse]'
```

SQLBuild talks to ClickHouse over HTTP or HTTPS. The oldest supported server is ClickHouse 25.8; older servers fail to connect with `A703`.

## Connection config

```toml
adapter = "clickhouse"
default_target = "dev"

[connections.clickhouse]
host = "localhost"
port = 8123
user = "default"
password = "${ENV:CLICKHOUSE_PASSWORD}"

[targets.dev]
connection = "clickhouse"
schema = "analytics_dev"
```

| Field | Description |
|-------|-------------|
| `host` | Server hostname (default: `localhost`) |
| `port` | HTTP port (default: `8123`, or `8443` with `secure = true`) |
| `user` | User name (default: `default`). Also accepts `username`. |
| `password` | Password |
| `database` | Database for unqualified names (default: `default`) |
| `secure` | Use HTTPS (default: `false`) |
| `verify` | Verify the server certificate over HTTPS (default: `true`) |
| `settings` | Extra ClickHouse settings applied to every query, as a table |
| `connect_timeout`, `send_receive_timeout` | Client timeouts in seconds |

Any other key fails with `A702`.

## Schemas are databases

ClickHouse has no level between a database and a table, so a SQLBuild **schema** is a ClickHouse **database**. Set `schema` on targets, models and sources; setting `database` fails with `A704`. SQLBuild creates model schemas with `CREATE DATABASE IF NOT EXISTS`.

Identifiers are case-sensitive in ClickHouse, quoted or not.

## How SQLBuild writes

SQLBuild never relies on background merges for correctness, and it never updates or deletes rows in place.

- **Tables** build in a staging table and replace the live table with `EXCHANGE TABLES`, which is atomic. This needs databases with the `Atomic` engine, the default; other engines fail with `A705`.
- **Views** use `CREATE OR REPLACE VIEW`.
- **Incremental `append`** inserts the new rows.
- **Incremental `merge`, `delete_insert` and cursor windows** rewrite whole partitions. SQLBuild stages the incoming rows, finds the partitions they touch and the partitions holding the rows they replace, rebuilds those partitions in a staging table, and swaps each one in with `ALTER TABLE ... REPLACE PARTITION`. Each swap is atomic. If a build stops before the swaps the table is untouched; if it stops between swaps, some partitions are already new, and rerunning the build recomputes the rest and converges.
- **Microbatches** use the same partition rewrite for each batch. Concurrent batches (`batch_concurrency`) rewrite different partitions in parallel; batches of one `sqb` process that share a partition take turns.

### One writer per model

A partition rewrite reads the partition, rebuilds it and swaps it in. ClickHouse has no transaction that spans those steps, and SQLBuild only serializes rewrites of the same partition inside one `sqb` process. If two `sqb` processes write the same model at the same time and touch the same partition, the later swap wins and the rows the other process wrote to that partition are lost.

Run each model from one process at a time: one scheduled job per model or per project, with no overlapping runs. Concurrency within a run (`--concurrency`, `batch_concurrency`) is safe.
- **Snapshots** apply their changes to a private copy of the snapshot table and exchange it in. Closing a version rebuilds the copy rather than updating rows, so the live snapshot changes only at the final exchange.

The cost of a rewrite is proportional to the partitions it touches. Without a `partition_by`, a table is one partition, so every incremental run rewrites the whole table; partition large incremental models by the column their new rows arrive on.

`merge` matches rows on `unique_key` exactly as other adapters do: incoming rows replace matched rows, `merge_exclude_columns` keep their stored values, and unmatched rows are inserted.

## Physical layout

Table and incremental models set their table engine, sorting key, partitioning, primary key and table settings in the MODEL header:

```sql
MODEL (
  description 'One row per order event.',
  materialized incremental,
  incremental_strategy delete_insert,
  unique_key [event_id],
  cursor event_time,
  cursor_type timestamp,
  cursor_inputs (raw_events event_time),
  engine 'ReplacingMergeTree(version)',
  order_by [event_id, event_time],
  partition_by 'toYYYYMM(event_time)',
  primary_key [event_id],
  table_settings (index_granularity 4096),
);
```

| Field | Value | Default |
|-------|-------|---------|
| `engine` | A single-server MergeTree-family engine, with its arguments | `MergeTree` |
| `order_by` | A sorting expression, or a list of them | `tuple()` (unsorted) |
| `partition_by` | A partitioning expression | No partitioning |
| `primary_key` | A prefix of `order_by` | The sorting key |
| `table_settings` | Setting names mapped to strings, integers or booleans | None |

Quote expressions that are not plain column names. Compile rejects malformed values, replicated and shared engines, and these fields on views and snapshots; other adapters reject them with `A011` when planning.

The fields are part of the model's version, so `sqb plan` reports a changed layout as a config change. A table model is rebuilt with the new layout. An incremental model keeps writing into its existing table with the old layout, and `sqb plan` warns with `PHYSICAL_LAYOUT_PENDING` until a full refresh (`sqb build <model> --full-refresh`, with `--start-cursor-ts` and `--end-cursor-ts` for a cursor model) rebuilds the table with the new layout.

ClickHouse rejects nullable sorting and partitioning keys by default. Wrap the column in `assumeNotNull()` or `coalesce()` in the expression, or set `table_settings (allow_nullable_key true)`.

## Reading ReplacingMergeTree sources

A `ReplacingMergeTree` table can hold several versions of a row until the server merges them in the background. Set `final true` on the source so every read SQLBuild generates for it uses `FINAL` and sees one version per key:

```yaml
sources:
  - name: customers
    description: Customer master data.
    schema: raw
    table: customers
    final: true
```

## Functions

SQL functions deploy as ClickHouse SQL user-defined functions (`CREATE FUNCTION name AS (args) -> expression`). ClickHouse function names are global to the server, not scoped to a database, so SQLBuild names each function `<schema>__<function>`. A function `half_amount` in schema `analytics` is created as `analytics__half_amount`, and `__udf("half_amount")` renders that name.

SQLBuild does not deploy Python functions (`A707`) or SQL table functions (`A708`) to ClickHouse: executable functions need server configuration files. Install them on the server and call them directly.

## Clones

`sqb clone` creates the clone with `CREATE TABLE ... AS` and attaches every part of the origin with `ALTER TABLE ... ATTACH PARTITION ALL FROM`, which hard-links the data instead of copying it. The clone keeps the origin's engine, keys and settings and stays valid after the origin is dropped.

## Settings SQLBuild pins

Every query runs with these settings so SQL behaves the same as on other adapters:

| Setting | Value | Why |
|---------|-------|-----|
| `join_use_nulls` | `1` | Outer joins return `NULL` for missing rows |
| `cast_keep_nullable` | `1` | `CAST` keeps `NULL` values |
| `union_default_mode`, `except_default_mode`, `intersect_default_mode` | `DISTINCT` | Bare `UNION`, `EXCEPT` and `INTERSECT` follow standard SQL |
| `default_table_engine` | `MergeTree` | Tables created without an engine clause are MergeTree tables |
| `mutations_sync`, `lightweight_deletes_sync` | `2` | Statements finish before the next one starts |
| `date_time_input_format`, `cast_string_to_date_time_mode` | `best_effort` | ISO 8601 timestamps with `T` and offsets parse |

Values under `settings` in the connection override these.

ClickHouse returns a type's default value (`0`, the epoch, an empty string) from `lag` and `lead` past the edge of a window frame unless the argument is `Nullable`. SQLBuild's generated snapshot SQL wraps those arguments in `toNullable` so they return `NULL` as on other adapters. Write the same in your own models when you rely on `NULL` there.

## Limits

- Single server only. `ON CLUSTER`, `ReplicatedMergeTree` and `Distributed` tables are not managed.
- No transactions. Each step above is designed so a rerun converges instead.
- Concurrent `sqb` processes writing the same model can lose rows; see [One writer per model](#one-writer-per-model).
- Snapshots always use an unsorted `MergeTree` table.
- Seeds load through the HTTP insert interface as CSV, so large seeds never hit the `max_query_size` limit.
- Retention and time travel are not available.
