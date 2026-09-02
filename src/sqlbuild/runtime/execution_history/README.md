# Execution history storage contracts

This package owns backend-neutral, append-only storage contracts for canonical
`LifecycleEvent` and `OpaqueLifecycleEvent` facts. Diagnostic and compute logs are separate concerns
and are never accepted by `EventLogStorage`.

## Durability and idempotency

`append_event` and `append_events` assign each newly durable fact a strictly increasing backend
`storage_order`, an opaque stable cursor, and a UTC `received_at`. Repeating an `event_id` with
canonically equivalent content is a no-op and returns the existing `StoredEvent`. Reusing an ID for
different canonical content raises `IntegrityConflictError` and cannot overwrite or otherwise
mutate the existing fact. The same rules apply to whole-batch retries. Normal storage APIs expose no
update or delete operation.

Pages are ascending. `after_cursor` is exclusive, `next_cursor` identifies the last returned record
and is `None` for an empty page, and callers must treat cursor encoding as implementation-owned.
Limits are positive and bounded by `MAX_PAGE_LIMIT`. Event timestamp ranges are inclusive. Event
cursors identify global storage positions and run cursors identify global `(created_at, run_id)`
sort keys. Both are filter-independent: a cursor remains valid when the next request changes its
filter, including when the cursor's record does not match that filter. Malformed cursors, cursors
from another backend, and cursors for positions absent from this storage raise `InvalidCursorError`.

Opaque filtering uses correctly typed stable envelope fields when present. `event_type`, `producer`,
`invocation_id`, and `run_id` must be non-empty strings to match their corresponding filters;
`occurred_at` must be a valid UTC timestamp to match a time range. A missing or malformed filtered
field does not match. An unfiltered query still returns the opaque fact unchanged.

## Run projection

Run storage is a rebuildable projection, never lifecycle authority. `project_runs` applies only
supplied durable `StoredEvent` facts in `storage_order`; `occurred_at` cannot reorder application.
Already-applied positions are ignored. A started run without a terminal fact remains `UNKNOWN` and
incomplete, and no terminal outcome is synthesized. If multiple terminal facts exist, the last one
in storage order wins deterministically. `created_at` is the first run fact's durable `received_at`,
which gives run paging the stable compound key `(created_at, run_id)`. Start and end times preserve
the corresponding facts' `occurred_at`. Optional command, target, and environment fields remain
`None` until canonical run-correlated facts provide them; projection metadata is never guessed.

Incremental projection and full rebuild must produce identical records. Opaque facts remain durable
but are not interpreted as known run semantics.

`RunStorage.project` and `RunStorage.rebuild_from_events` publish atomically. A call either publishes
all projection changes computed from its supplied durable facts or publishes none of them. A retry
or full rebuild against the durable event log repairs a failed publication; consumers can never
observe a prefix of one projection call. Storage lifecycle is symmetric: both stores support
idempotent `close`, `dispose`, and context management. Schema inspection and upgrades preserve all
facts and projections; the current/default target is idempotent and unsupported zero, past, or
future targets raise `UnsupportedSchemaVersionError` without mutation.

## Transactions and reconciliation

`append_and_project` always appends before projection. If append fails, projection is not called. If
append commits and projection fails, the event log remains authoritative and replay through
`rebuild_from_events` repairs the projection. A backend should append and project in one transaction
when both stores share transactional infrastructure, but correctness cannot depend on that
optimization. Projection must never publish facts that did not durably append.

The intended local default backend is SQLite and the intended deployed backend is PostgreSQL. Those
adapters are separate follow-up work. This core has no object-store, Kafka, ClickHouse, Dagster,
SQLite driver, or PostgreSQL driver dependency.
