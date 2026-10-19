<!-- generated-by: sqlbuild skills -->

# sqb recall

> Query the recorded history of past invocations.

Online: https://sqlbuild.com/docs/cli/recall/

## Contents

- Usage
- sqb recall query
- sqb recall schema
- sqb recall output
- Errors

Read the local [Recall](../concepts/observability/recall.md) store: past invocations, the
statements they executed, and what they printed. `sqb recall` never records itself.

## Usage

```bash
sqb recall query "SELECT command, status, duration_ms FROM invocations ORDER BY invocation_started_at DESC"
sqb recall schema
sqb recall output last
```

## sqb recall query

Run one read-only SQLite `SELECT` against the Recall views. Statements that write, and multiple
statements, are rejected.

| Flag | Description |
|------|-------------|
| `sql` | The query (positional argument) |
| `--format` | `long` (default), `table`, `json`, or `csv` |
| `--json` | Shorthand for `--format json` |
| `--limit` | Maximum rows to return (default: 100) |
| `--no-limit` | Disable the row limit |
| `--max-cell-bytes` | Longest cell in text formats, in bytes (default: 4096; `0` for no limit) |
| `--target` | Target whose store to read (default: the default target) |
| `--backend` | `logs` (default) reads the Recall store; `warehouse` runs the query on the target's connection |

The latest invocation in a project named `orders_shop`:

```bash
sqb recall query --format table \
  "SELECT command, status, exit_code, duration_ms FROM invocations
   ORDER BY invocation_started_at DESC LIMIT 1"
```

```
command | status    | exit_code | duration_ms
------- | --------- | --------- | -----------
build   | completed | 0         | 752.0

1 row
```

The slowest statements of past builds, with their SQL:

```bash
sqb recall query --format table --max-cell-bytes 60 \
  "SELECT s.resource_name, round(s.duration_ms, 1) AS ms, a.text AS sql
   FROM statements s JOIN artifacts a USING (invocation_id, statement_id)
   WHERE s.statement_kind = 'CREATE' ORDER BY s.duration_ms DESC LIMIT 2"
```

```
resource_name | ms  | sql
------------- | --- | ------------------------------------------------------------------------
orders        | 3.6 | CREATE OR REPLACE TABLE dev.orders__staging AS SELECT 1 …[+74 bytes]
NULL          | 3.2 | CREATE SCHEMA IF NOT EXISTS dev

2 rows
```

Failed invocations of the last week:

```bash
sqb recall query \
  "SELECT invocation_id, command, error_code FROM invocations
   WHERE status = 'failed' AND invocation_started_at >= strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-7 days')"
```

Timestamps are ISO-8601 UTC text, so they compare correctly as strings. Filter on
`invocation_started_at` to bound a scan.

## sqb recall schema

List every Recall view with its columns, types, and join keys. Accepts `--format`, `--json`, and
`--target`. With `--backend warehouse`, it lists SQLBuild's state tables in the target's warehouse
instead, or describes one with `--relation <name>`.

## sqb recall output

Print what an invocation wrote, byte for byte.

```bash
sqb recall output last                       # the latest invocation, both streams in order
sqb recall output 7607b5b6 --stream stderr   # an invocation ID or unique prefix
sqb recall output last --tail 20             # only the last 20 lines
```

| Flag | Description |
|------|-------------|
| `invocation` | Invocation ID, unique prefix, or `last` (default) |
| `--stream` | `combined` (default), `stdout`, or `stderr` |
| `--tail` | Print only the last N lines |
| `--target` | Target whose store to read |

Output that Recall could not record completely is followed by a note on stderr naming the gap.

## Errors

| Code | Meaning |
|------|---------|
| `C970` | Recall is disabled for this project or target |
| `C971` | The store cannot be read, or no history is recorded yet |
| `C972` | No invocation matches |
| `C973` | The invocation prefix matches more than one invocation |
| `C974` | The query is invalid or not read-only |
| `C975` | The `[recall]` settings are invalid |
