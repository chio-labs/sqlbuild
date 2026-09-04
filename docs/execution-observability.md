# Execution observability

SQLBuild deliberately separates execution facts from logs and output projections. Choose the
record that answers the question instead of treating every JSON or log file as interchangeable.

## Records and authority

| Record | Purpose | Authority and retention |
| --- | --- | --- |
| `LifecycleEvent` | Immutable facts about invocation, run, resource-attempt, operation, retry, and statement lifecycles | Canonical execution evidence. An explicitly attached `EventLogStorage` is authoritative once the fact is durable. SQLite and PostgreSQL retain facts until an operator removes the database or applies an external retention policy. |
| `DiagnosticLog` | Structured framework and user diagnostics | Explanatory only. It cannot establish that work started, completed, failed, skipped, or retried. Local compute-log retention applies. |
| `stdout.log` and `stderr.log` | Exact process output for one invocation | Troubleshooting data, not execution truth. Local compute-log retention applies. |
| `CommandOutputRecord` | Normalized, ANSI-free, line-oriented stdout/stderr chunks for an explicitly configured remote sink | Potentially sensitive, bounded, and potentially lossy troubleshooting data. It is not execution evidence and destination retention is project-owned. |
| `target/run/` | Full executed model, function, and test SQL, Python-check output, and scenario artifacts | Sensitive, command-written runtime artifacts. This shared tree is not invocation-isolated and may be replaced by later commands. It is not lifecycle truth. |
| `target/executions/<run_id>/statements.jsonl` | Best-effort run statement ledger with statement/resource identity, status, timing, query ID, and SQL SHA256 | A run-owned cost/query-ID input. It omits SQL text and does not establish lifecycle status. SQLBuild has no automatic retention for this tree. |
| `RunRecord` | Current run summary rebuilt from durable run facts | Disposable serving state. Rebuild it from the event log; never use it as the only lifecycle authority. |
| Integration-result JSONL | Bounded resource terminal plus integration enrichment | Canonical SQLBuild-owned integration side channel, but still a projection/consumer of lifecycle facts rather than event history. |
| Final `--json` or `--json-output` document | Aggregate command result | A separate end-of-command projection. It is not enabled by integration-result output and is not lifecycle authority. |

Compute logs, command-output records, final output, full SQL artifacts, user messages, and
Python/check metadata can contain sensitive data. Lifecycle, integration-result, and sink-health records intentionally exclude
full SQL, parameter values, credentials, arbitrary user messages, and unbounded metadata.

## Lifecycle envelope

Schema version 1 has these fields:

```json
{
  "event_id": "9fb6d899754d4bd79c703067a8d5046c",
  "event_type": "statement_completed",
  "schema_version": 1,
  "producer": "sqlbuild",
  "producer_version": "1.2.3",
  "occurred_at": "2026-09-02T10:15:30.125000+00:00",
  "invocation_id": "4cc757dd93fe466aad2a220f1e76625e",
  "run_id": "run-20260902-101500",
  "resource_id": "model:orders",
  "resource_attempt_id": "97933c4aa29441cda133641345515e20",
  "operation_id": "c978e47367494051bdde68ad03e56db4",
  "statement_id": "5113ebc5afe247eb9c41dc0b27ef1a9a",
  "payload": {
    "adapter": "snowflake",
    "duration_ms": 318.4,
    "query_id": "01b6f1c2-0000-0000-0000-000000000000",
    "sql_digest": "881b77b00a75e07936d7f20ea308a55e9ef98f2f1fd42c144a3a998d32094c1b"
  }
}
```

`event_id` identifies immutable content. Re-appending canonically equal content with the same ID is
an idempotent no-op; different content under that ID is an integrity error. `producer` and
`producer_version` identify the emitting implementation, while `schema_version` identifies the
wire contract. Known schema-v1 events reject unknown envelope and payload fields. Readers preserve
unknown event names or newer schema versions as opaque envelopes rather than inventing semantics.
History storage retains those opaque envelopes and exposes them to queries, but run projection,
native progress, integration-result output, and lifecycle-event sinks consume only known
`LifecycleEvent` values and ignore opaque facts.

An invocation ID exists for every fact. A run groups executable graph work. A stable `resource_id`
identifies the logical model, source, check, or other resource, while a new
`resource_attempt_id` identifies each attempt. `operation_id` identifies one blocking non-SQL
operation and `statement_id` one SQL statement. IDs are correlation values, not timestamps.

Publication is synchronous and preserves each producer's call order. Concurrent producers have no
global event-time ordering guarantee. Durable `storage_order` is the total order assigned by one
storage backend; `occurred_at` never reorders it. Starts and `statement_submitted` are nonterminal.
Completed, failed, and `resource_attempt_skipped` facts are terminal. `retry_scheduled` is a
first-class fact between attempts. A start without terminal evidence remains unknown or presumed
lost: no storage, projection, integration, or sink may fabricate success or failure.

## Integration consumers

`SQLBUILD_INTEGRATION_RESULT_PATH` (or SQLBuild's integration-owned hidden `--event-output` route)
enables schema-v1 `integration_result` JSONL. Each record contains the canonical resource-terminal
identity and bounded asset or check enrichment. The envelope fields are `schema_version`,
`record_kind`, `event_id`, `event_sequence`, `event_type`, `occurred_at`, all lifecycle correlation
IDs, resource kind/name, attempt number, duration, output kind, command, bounded failure or skip
codes, and one asset or check result.

The writer claims each matching resource-attempt terminal once. Retries correlate through the same
resource ID and distinct attempt IDs; the latest exact terminal is claimed. Physical JSONL order is
result-callback order. `event_sequence` is the zero-based position among unique, known lifecycle
events observed by that invocation's in-memory terminal index. It excludes duplicate publications
and opaque facts, and it is neither durable `storage_order` nor a cross-process ordering key. Use it
to restore the terminal index's observed order among records from the same invocation. A result
callback without matching terminal evidence emits no record, and final aggregate JSON omits that
incomplete resource rather than inventing an outcome. Closing the writer emits nothing.

An explicit writer path takes precedence over `SQLBUILD_INTEGRATION_RESULT_PATH`. Integration-result
files are opened in append mode, so an integration that reuses a path must truncate or rotate it
before starting a new invocation. The hidden `--event-output` transport option is available only on
`build` and `clone`; other producers use the environment-owned path. Final `--json-output` is a
different path: it overwrites its destination, and when supplied with `--json` it suppresses the
aggregate document on stdout.

The Dagster adapter owns creation and consumption of this side channel. At a high level it streams
each validated envelope into Dagster asset materializations and checks, then uses the separate final
aggregate JSON only where end-of-command enrichment is still needed. The removed Dagster live v1
JSONL format is neither authoritative nor supported; CHI-192 replaced it with integration-result
envelopes.

## Local paths and troubleshooting

For a command started on 2 September 2026 with invocation ID `INVOCATION_ID`, inspect:

```text
logs/2026-09-02/INVOCATION_ID/
  metadata.json
  stdout.log
  stderr.log
  diagnostics.jsonl
  complete
target/run/
target/executions/<run_id>/statements.jsonl
```

`metadata.json` initially records the invocation, command, resolved project directory, UTC start
date/time, optional selected target, and the run ID if one already exists at capture setup. On a
clean close SQLBuild atomically replaces it with final metadata containing completion time, exit
code, and stream byte counts, then creates the empty `complete` marker. The marker proves only that
capture finalized; it is not lifecycle completion evidence. Its absence means the capture is live
or abandoned, not that execution failed.

Use the supported API to inventory and follow exact stream bytes:

```python
from pathlib import Path

from sqlbuild.compute_logs import ComputeLogStream, open_local_compute_log_storage

with open_local_compute_log_storage(project_dir=Path(".")) as logs:
    for capture in logs.inventory().captures:
        print(capture.invocation_id, capture.is_complete, capture.path)

    cursor = 0
    while True:
        chunk = logs.read(
            invocation_id="INVOCATION_ID",
            stream=ComputeLogStream.STDERR,
            cursor=cursor,
        )
        print(chunk.data.decode("utf-8", errors="replace"), end="")
        cursor = chunk.next_cursor
        if chunk.is_complete and not chunk.data:
            break
```

Byte cursors are nonnegative exact offsets in one stream; they are not event cursors. Reads are
bounded to 1 MiB. The default prune policy retains the newest 20 complete captures and never removes
incomplete captures. CLI-managed capture calls `prune()` after successful finalization. Direct API
users must call `prune()` themselves; setting `retention_count=None` makes that call a no-op.

The local files are host-local. The compute-log implementation rejects symlink roots and path
escapes but does not force file modes; permissions follow directory ownership and the process umask.
Set a restrictive umask and secure or encrypt the host volume. Operators must secure parent
directories, backups, `logs/`, and `target/`. An explicitly constructed SQLite history creates
`.sqlbuild/` with mode `0700` when new and applies mode `0600` to `history.sqlite3`; the CLI does not
construct execution-history storage implicitly.

SQLBuild does not write a shared `target/sqlbuild.log`. Use the invocation-specific paths above so
concurrent and historical command diagnostics remain isolated. Project-creation commands (`sqb
init`, `sqb playground`, and `sqb dbt init`) create none of these runtime paths in the destination
before project creation.

## Target layout

`target/` contains disposable generated artifacts and caches:

| Path | Contents |
| --- | --- |
| `target/cache/compiler/` | Regenerable compiler analysis, SQL-reference, and declaration-scope caches. |
| `target/compiled/` | Human-inspectable compiled models, functions, audits, and tests. |
| `target/run/` | Latest command's executable SQL and runtime artifacts; shared and replaceable. |
| `target/executions/<run_id>/` | Per-run statement ledgers and cost records. |
| `target/manifest.json` | Compiled project manifest when requested. |
| `target/sqlbuild_dag.json` | Dagster-facing project DAG artifact when requested. |

All cache and execution paths under `target/` may be removed and regenerated. SQLBuild does not
read compatibility paths such as `target/compile-cache/`, `target/runs/`, or the removed dbt reuse
cache under `target/sqlbuild/`.

## Failure behavior

| Failure | Evidence and command effect |
| --- | --- |
| Explicit lifecycle storage unavailable | Direct storage API calls raise `ExecutionHistoryStorageError`; the CLI does not select a backend implicitly. |
| Lifecycle storage append fails | The dispatcher isolates the explicitly attached history subscriber and command work continues. The missing fact cannot be recovered from a projection. |
| Compute-log open or write fails | SQLBuild reports best-effort diagnostics, preserves console operation, and preserves the command result. The capture may be absent or incomplete. |
| Integration-result path creation, open, append, flush, or close fails | The error is not best effort and can fail the command or integration-output phase. The JSONL file may contain a valid prefix. |
| Final `--json-output` directory creation or write fails | The error can fail the command output phase. SQLBuild does not claim that the aggregate document was published. |
| Exporter module discovery, declaration validation, provider construction, or provider setup fails | Startup fails before command execution because project extension configuration is invalid. |
| Export queue overflow or priority displacement | Eligible attempts are counted `dropped`; command correctness is unchanged. |
| Exporter raises or times out | The attempt is counted `failed`; that exporter is isolated and a timed-out exporter is blocked from later calls. Command correctness is unchanged. |
| Exporter hangs forever | Its daemon thread may remain alive and retain the shared provider session until process exit. Shutdown remains bounded and `flush_complete` is false. |
| Failure/health notification callback fails or blocks | It is isolated on a daemon worker. Failure notices may be dropped and periodic health is coalesced; command and exporter delivery continue. |
| Process interruption | Terminal facts and compute-log `complete` may be absent. Treat affected scopes as unknown, and never infer failure solely from missing evidence. |
| Exporter shutdown deadline expires | Queued and unattempted eligible pairs become `dropped`; timed-out attempts are `failed`; `flush_complete` is false. Command correctness is unchanged. |

Observability degradation does not turn successful warehouse work into failure. Conversely, a clean
log or exporter return does not prove command success. Extension discovery/setup is different: an
invalid configured project extension prevents the command from starting.

## Explicit exclusions

This foundation does not provide a SQLBuild UI or API server, scheduler, sensors, remote agents,
launch/cancel control plane, durable exporter spool, object-storage compute logs, or core
Kafka/ClickHouse integration. Kafka, ClickHouse, and other exporter destinations are project-owned.

See [execution history](execution-history.md) for storage APIs and
[typed sinks](sinks.md) for lifecycle-event and command-output delivery semantics.
