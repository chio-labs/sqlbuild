# Typed sinks

Project sinks consume one declared record type. Lifecycle-event and command-output contracts are
separate even when both sinks use the same provider instance and remote service. Delivery is
bounded, isolated, destination-neutral, and best effort. A sink cannot change an execution result
and is not durable history.

The former `sqlbuild.event_exporters`, `sqlbuild.output_capture`, `event_exporters/`, and
`[event_exporters]` interfaces have been replaced. Move declarations to `sinks/`, import the typed
APIs below from `sqlbuild.sinks`, and move lifecycle filters to `[sinks.lifecycle]`. Legacy project
directories and configuration fail with an explicit migration error rather than silently disabling
publication.

## Declare a lifecycle-event sink

SQLBuild imports public `sinks/**/*.py` files in sorted path order. It ignores
`__init__.py` and any file below a path component beginning with `_`. Only functions defined in the
module and decorated with the public API are sinks.

```python
# sinks/publish.py
from providers.destination_client import DestinationClient
from sqlbuild.sinks import (
    LifecycleEvent,
    LifecycleEventKind,
    lifecycle_event_sink,
    lifecycle_event_to_json,
)


@lifecycle_event_sink(
    name="publish_lifecycle",
    event_kinds={LifecycleEventKind.RUN, LifecycleEventKind.RESOURCE, LifecycleEventKind.AUDIT},
    min_severity="info",
)
def publish_lifecycle(
    event: LifecycleEvent,
    destination_client: DestinationClient,
) -> None:
    destination_client.publish(
        route="sqlbuild.lifecycle.v1",
        key=event.event_id,
        payload=lifecycle_event_to_json(event).encode("utf-8"),
    )
```

The function must be synchronous, declare `event` first, use only named parameters, have no
defaults or variadics, and return `None` if annotated. `event` may be unannotated or exactly
`LifecycleEvent`. Every later parameter is injected by provider name and may be unannotated or
annotated with exactly that discovered provider class. Sink names are unique lower-snake-case
identifiers; the default name is the function name.

## Declare a command-output sink

Remote stdout/stderr publication is disabled unless a public function under `sinks/` is explicitly
decorated with `@command_output_sink`. Lifecycle-event sinks never receive command output.

```python
# sinks/publish.py
from providers.destination_client import DestinationClient
from sqlbuild.sinks import (
    CommandOutputRecord,
    command_output_sink,
    command_output_to_json,
)


@command_output_sink(name="publish_command_output", streams={"stdout", "stderr"})
def publish_command_output(
    record: CommandOutputRecord,
    destination_client: DestinationClient,
) -> None:
    destination_client.publish(
        route="sqlbuild.command_output.v1",
        key=record.record_id,
        payload=command_output_to_json(record).encode("utf-8"),
    )
```

The function must be synchronous, declare `record` first, and follow the same provider-parameter
rules as a lifecycle sink. `streams` defaults to both streams and may explicitly narrow delivery to
`stdout` or `stderr`. Loss summaries are delivered to every command-output sink because a shared
bounded queue can lose records from either stream.

`CommandOutputRecord` is a canonical versioned envelope. Records are ANSI-free, line-oriented,
UTF-8-size-bounded chunks with invocation/run correlation, per-invocation sequence, stream,
chunk position, producer metadata, and opaque JSON-compatible integration context. A
`command_output_loss` record reports bounded-queue loss. This stream is troubleshooting data: it is
potentially sensitive, may be lossy, and is not execution evidence. Exact host-local bytes remain in
the invocation's `stdout.log` and `stderr.log` compute logs.

A minimal destination-neutral provider shape is:

```python
# providers/destination_client.py
from sqlbuild.providers import Provider


class DestinationClient(Provider):
    provider_name = "destination_client"

    def setup(self, ctx: object | None) -> None:
        del ctx
        # Create the project-owned SDK client from secret-resolved settings here.

    def publish(self, *, route: str, key: str, payload: bytes) -> None:
        del route, key, payload
        # Route, key, serialization, retries, acknowledgements, and durability are project policy.

    def teardown(self) -> None:
        # Close the project-owned SDK client here.
        pass
```

The example uses released SQLBuild imports and exact discovery signatures. Replace only the method
bodies with a project-owned destination SDK. SQLBuild owns event validation/redaction and local
dispatch; the project owns destination client settings, credentials, topic/route, key,
serialization, retry, acknowledgement, and durability.

## Runtime filters

Declaration filters opt in; runtime configuration can only narrow them:

```toml
[sinks.lifecycle]
event_kinds = ["run", "resource", "operation", "statement"]
min_severity = "info"

[sinks.lifecycle.named.publish_lifecycle]
event_kinds = ["resource", "statement"]
min_severity = "warning"
```

Effective kinds are the intersection of declaration, global, and named sets. Effective minimum
severity is the strictest of all three. Omitting declaration options means all kinds at `debug`.
Unknown lifecycle sink names, keys, kinds, or severities fail before execution.
Python declarations should use `LifecycleEventKind`; TOML continues to use the corresponding string
values. The `audit` kind carries `audit_completed` after an audit outcome is confirmed. Its payload
includes audit and attachment identity, evaluation mode, outcome and severity, run scope, optional
measurement/sample/threshold summary, bounded evidence metadata and rendered audit SQL diagnostics.

| Lifecycle event | Export kind | Severity | Queue priority |
| --- | --- | --- | --- |
| `invocation_started` | `invocation` | `debug` | 0 |
| `run_started` | `run` | `debug` | 0 |
| `resource_attempt_started` | `resource` | `debug` | 0 |
| `operation_started` | `operation` | `debug` | 0 |
| `statement_started`, `statement_submitted` | `statement` | `debug` | 0 |
| `retry_scheduled` | `retry` | `warning` | 1 |
| `audit_completed` | `audit` | `info` | 2 |
| `invocation_completed`, `run_completed`, `resource_attempt_completed`, `resource_attempt_skipped`, `operation_completed`, `statement_completed` | Corresponding kind | `info` | 2 |
| Any `*_failed` event | Corresponding kind | `error` | 3 |

Diagnostics and command output never enter lifecycle-event queues.

## Discovery and provider lifetime

Startup first imports sink modules and collects declarations without framework provider discovery.
If there are no decorated public sinks, SQLBuild does not discover, construct, or set up providers
and does not create delivery threads. Sink modules are ordinary Python modules, so
their own imports and import-time side effects still run; keep declarations import-safe. Otherwise
normal project discovery finds provider classes, validates name/type
injection, constructs providers, and calls each required provider's `setup` at most once on first
use. Shared providers are torn down once in reverse setup order.

Shutdown stops lifecycle-event acceptance, performs a bounded drain, and only then requests provider
teardown. Each lifecycle sink invocation runs on its own daemon isolation thread. A call has a one-second
default timeout; after timeout that sink is blocked from later invocations. Python cannot kill
the thread or reverse destination side effects. Provider teardown is deferred until all live
invocations return, so a forever-hung daemon retains its provider session until process exit. A
provider is never torn down while live sink code can access it. Command-output capture has its own
bounded queue, batching, and shutdown deadline, then uses the already-bound command-scoped provider
instances.

## Queueing and accounting

One command owns one daemon dispatcher and a queue of 1024 events by default. Dispatch always takes
the highest priority and is FIFO by canonical enqueue sequence among equal priorities. If full, a
higher-priority arrival displaces the oldest queued event at the lowest lower priority. An arrival
that is not higher priority is dropped. Filtering happens before queueing, and each queued event
carries its exact eligible exporter set, preventing duplicate attempts during fanout or displacement.

For every event/exporter pair exactly one rule applies:

```text
filtered += 1

or

accepted += 1
accepted ends in exactly one of delivered, failed, or dropped
```

Every final per-exporter and aggregate snapshot therefore satisfies:

```text
accepted == delivered + failed + dropped
```

`delivered` means only that the project callable returned normally. It does not prove remote
acknowledgement, persistence, deduplication, or exactly-once delivery unless project code establishes
those properties.

Health defaults to 30 seconds and emits only after counters or queue depth change. A single pending
periodic slot is overwritten by the latest snapshot while notification is blocked, so health is
coalesced rather than backlogged. Failure notices use a separate bounded queue and may be dropped.
The final summary has a retained write-once slot. Notification callbacks run on one daemon worker;
exceptions are swallowed, and shutdown does not wait for callbacks.

Nonfinal health always has `flush_complete=false`. Final `flush_complete=true` means the dispatcher
stopped, no exporter invocation remains live, the queue is empty, and all accepted pairs satisfy the
accounting invariant. A timed-out live invocation makes it false even though that attempt is
`failed` and later/queued attempts are `dropped`.

## Security and failure boundaries

Lifecycle payloads have a catalogued allowlist. They contain no full SQL, parameter values,
credentials, arbitrary user messages, raw process output, destination details, or provider settings.
Exporter failure and health diagnostics include only exporter name, event kind/severity, exception
type, counters, and queue dimensions. They bypass lifecycle publication and exporter enqueue to
prevent recursion.

Do not enrich exported events from `target/run/`, compute logs, final JSON, environment variables,
or provider secrets unless the destination has an explicit sensitive-data policy. Restrict
destination credentials and permissions to only the routes and operations this exporter needs.

Discovery, declaration, configuration, provider construction, and provider setup errors are project
configuration errors and prevent command execution. Queue overload, exporter exceptions, timeouts,
hung calls, notification failures, and incomplete shutdown affect only best-effort export. Consult
the [failure matrix](execution-observability.md#failure-behavior) for operator response.

SQLBuild core intentionally provides no durable spool and no Kafka or ClickHouse implementation.
See [execution observability](execution-observability.md) and
[execution history](execution-history.md) for canonical authority and durable storage.
