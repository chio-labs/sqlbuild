# Runtime observability contracts

This package defines wire contracts only. It does not dispatch, store, route, or render records.

## Execution identity

Runtime correlation uses one immutable `ExecutionIdentity` snapshot backed by a scoped context
variable. Invocation identity is required; run, resource, resource-attempt, operation, statement,
and diagnostic log-stream identities are optional. Resource and resource-attempt IDs remain
separate. Explicit non-empty string IDs are preserved exactly, including SQLBuild run IDs, while
new invocation, resource-attempt, operation, statement, and log-stream IDs use `uuid4().hex`.

## Lifecycle facts

Schema version 1 uses an immutable envelope with `event_id`, `event_type`, `schema_version`,
`producer`, `producer_version`, UTC `occurred_at`, required `invocation_id`, optional `run_id`,
`resource_id`, `resource_attempt_id`, `operation_id`, and `statement_id` correlations, and a
JSON-compatible `payload` object.

The v1 event catalog is:

- Invocation: `invocation_started`, `invocation_completed`, `invocation_failed`
- Run: `run_started`, `run_completed`, `run_failed`
- Resource attempt: `resource_attempt_started`, `resource_attempt_completed`,
  `resource_attempt_failed`
- Operation: `operation_started`, `operation_completed`, `operation_failed`
- Statement: `statement_started`, `statement_submitted`, `statement_completed`,
  `statement_failed`

Known events are validated against catalogued correlations and safe payload fields. Statement
facts never contain full SQL text or parameter values. Query text, parameters, credentials, and
other sensitive or high-cardinality details must not be added to lifecycle payloads.

Statement facts may carry `intent`, `sql_digest`, warehouse `job_id`, `query_id`, `row_count`,
`affected_rows`, `batch_size`, and a JSON object `metadata` of at most 4096 bytes in deterministic
encoded form. Counts are nonnegative integers and durations are nonnegative finite milliseconds.

Completed and failed facts are terminal for their correlated scope. Started and submitted facts
are not terminal. Facts are append-only. Re-publication of a byte-equivalent fact with the same
`event_id` is idempotent; reuse of an ID for different content is a contract violation.

Consumers must treat unknown event names and schema versions as opaque envelopes. Compatible
additions happen through catalogued payload fields or new event names. Known v1 envelopes reject
unknown top-level fields; incompatible envelope changes require a new schema version.

## Diagnostic logs

Diagnostic schema version 1 is structurally separate from lifecycle facts. Its envelope contains
`severity`, `logger`, `source`, `message`, JSON-compatible `fields`, producer and UTC timestamp
metadata, and optional `log_stream_id` plus lifecycle correlation IDs. Logs explain behavior but
are not lifecycle facts and cannot establish completion or failure semantics.

SQLBuild's structured `log_sql` and `log_debug_event` helpers attach the current execution identity.
Arbitrary raw calls to Python's `logging` API are not automatically correlated; that integration is
deferred to CHI-176 rather than installing a global logging filter here.
