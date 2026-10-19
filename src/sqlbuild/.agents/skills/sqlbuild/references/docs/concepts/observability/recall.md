<!-- generated-by: sqlbuild skills -->

# Recall

> The local history of every command: what ran, what it executed, and what it printed.

Online: https://sqlbuild.com/docs/concepts/observability/recall/

## Contents

- What is recorded
- Settings
- Output limit
- Retention
- When the store cannot be written
- Querying history
- Relationship to compute logs

Recall records each `sqb` invocation in a local SQLite store so you can ask what happened after the
fact: which command ran, how it ended, which statements it executed and how long they took, and
exactly what it printed. Recall is on by default and needs no setup.

## What is recorded

For every recorded invocation, Recall keeps:

- the invocation itself: command, arguments, target, adapter, status, exit code, and timing;
- its [lifecycle events](../observability.md): runs, resource attempts, statements,
  retries, and audit results;
- the SQL text of every executed statement, stored once per distinct statement and shared across
  invocations;
- its stdout and stderr, byte for byte, in the order they were written, up to
  [`max_output_bytes`](#output-limit) of each stream;
- framework diagnostics at or above `diagnostics_min_severity`.

Writes happen on a background thread and never fail the command. A command that cannot record all
of its history still succeeds, prints a warning followed by its own final status, and
`output_invocations` reports the gap. An invocation whose process died without finishing has
status `abandoned`.

Every command is recorded except `sqb recall` itself, commands that create a project (such as
`sqb init`), and raw-query `sqb diff`. A `sqb compile` answered from the launcher's warm cache is not
recorded either.

The store is `logs/recall.sqlite3` in the project directory. Add `logs/` to `.gitignore`; the store
can contain sensitive SQL and output.

## Settings

Configure Recall in `[recall]` in `sqlbuild_project.toml`. A `[targets.<name>.recall]` table
overrides individual keys for one target.

```toml
[recall]
retention = "30d"             # days of history to keep; also accepts hours, such as "720h"
shutdown_timeout = "3s"       # longest delay Recall may add when a command exits
diagnostics_min_severity = "info"
max_output_bytes = 2097152    # bytes of each output stream to keep; 0 keeps everything

[targets.ci.recall]
enabled = false               # do not record runs against the ci target
```

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `true` | Set to `false` to stop recording |
| `connection` | (none) | A `sqlite` connection whose `path` names the store; defaults to `logs/recall.sqlite3` |
| `retention` | `"30d"` | How long invocations are kept, in days (`d`) or hours (`h`), up to 3650 days |
| `shutdown_timeout` | `"3s"` | The cap on time spent flushing history at exit, in `s` or `ms`, up to 10 minutes |
| `diagnostics_min_severity` | `"info"` | `trace`, `debug`, `info`, `warning`, `error`, or `critical` |
| `max_output_bytes` | `2097152` for the local store | Bytes of stdout and of stderr kept per invocation, an integer; `0` keeps everything. See [Output limit](#output-limit) |

To turn Recall off for the whole project:

```toml
[recall]
enabled = false
```

Recall never delays the start of a command. At exit it waits at most `shutdown_timeout` for queued
history to reach the store; anything left is counted as dropped. A second Ctrl-C stops waiting at
once.

## Output limit

Recall keeps at most `max_output_bytes` of each output stream per invocation: the first half and
the last half, byte for byte. The local SQLite store defaults to 2 MiB, so a command that prints
more keeps its first and last MiB of stdout and of stderr. Set `max_output_bytes = 0` to keep
everything, or a larger number to keep more; a `[targets.<name>.recall]` table can set it for one
target. The command itself prints nothing about the limit.

The middle that was left out is one gap: `output_invocations` reports `gap_reason = 'truncated'`,
the left-out byte count in `truncated_bytes`, and `complete = 0`. `sqb recall output` prints a
note in its place:

```
… 23.6 MB of stdout not recorded (kept the first and last 1 MiB). Raise [recall] max_output_bytes to keep more.
```

The end of a stream is held in memory until the command exits, so a process that is killed keeps
only the first half.

## Retention

Commands occasionally prune invocations older than `retention`, with all of their events, output,
and diagnostics. SQL text is removed once no remaining invocation references it. Pruning runs in
the background within the exit budget and never removes an invocation that is still running.

## When the store cannot be written

If the store location is not writable, the command still runs and prints a notice on stderr with
the SQL an administrator can use to create the store; the notice comes before the command's own
output whenever the problem is visible from file permissions. The notice
repeats at most once a day. If the store file is not a SQLite database, Recall moves it aside to
`recall.sqlite3.corrupt-<UTC timestamp>`, starts a fresh store, and says so once. Commands that
find the same corrupt file coordinate through `recall.sqlite3.lock`, so only one of them moves it.

A `connection` that does not use the `sqlite` adapter is not supported yet; Recall prints a notice
and records nothing.

## Querying history

Use [`sqb recall`](../../cli/recall.md) to read the store. Queries are read-only SQLite `SELECT`
statements against these views:

| View | One row per |
|------|-------------|
| `invocations` | Invocation, with status, exit code, and timing |
| `statements` | Executed statement, with resource, kind, purpose, duration, and row counts |
| `audit_results` | Evaluated audit |
| `events` | Lifecycle event |
| `diagnostics` | Retained diagnostic |
| `artifacts` | Reference from an invocation to captured SQL, with its text |
| `output_invocations` | Invocation's output, with completeness |
| `output_transcripts` | Invocation's stdout, stderr, and combined output |
| `output_tail` | Recent output chunk |
| `conflicts` | Record written twice with different content |

Run `sqb recall schema` for every column.

## Relationship to compute logs

Compute logs (`logs/<date>/<invocation_id>/stdout.log`, `stderr.log`, and `diagnostics.jsonl`) are
still written alongside Recall. Recall stores the same output bytes, captured at the same point, so
`sqb recall output` matches the compute log files.
