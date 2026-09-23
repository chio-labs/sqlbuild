<!-- generated-by: sqlbuild skills -->

# Typed Sinks

> Export lifecycle facts and command output through project-owned providers.

Online: https://docs.sqlbuild.com/concepts/observability/sinks

Project sinks consume one declared record type. Lifecycle and command-output streams remain separate
even when they share a provider and destination.

## Lifecycle sink

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
    event_kinds={
        LifecycleEventKind.INVOCATION,
        LifecycleEventKind.RUN,
        LifecycleEventKind.RESOURCE,
        LifecycleEventKind.AUDIT,
    }
)
def publish_lifecycle(event: LifecycleEvent, destination_client: DestinationClient) -> None:
    destination_client.publish(
        route="sqlbuild.lifecycle.v2",
        key=event.invocation_id,
        payload=lifecycle_event_to_json(event).encode("utf-8"),
    )
```

Using `invocation_id` as a partition key keeps one invocation on one Kafka partition. Keep
`event_id` in the payload as the deduplication identity. Confirm the destination topic is not
compacted when complete lifecycle history must remain replayable.

## Command-output sink

```python
from sqlbuild.sinks import CommandOutputRecord, command_output_sink, command_output_to_json

@command_output_sink(streams={"stdout", "stderr"})
def publish_output(record: CommandOutputRecord, destination_client: DestinationClient) -> None:
    destination_client.publish(
        route="sqlbuild.command_output.v1",
        key=record.record_id,
        payload=command_output_to_json(record).encode("utf-8"),
    )
```

Command output groups adjacent text into bounded byte chunks and flushes on elapsed time, stream
change, size, or close. A loss record reports bounded-queue drops. This stream is useful for remote
transcripts but is not lifecycle evidence.

## Configuration

Runtime configuration can narrow declaration filters:

```toml
[sinks.lifecycle]
event_kinds = ["run", "resource", "operation", "statement", "audit"]
min_severity = "info"

[sinks.lifecycle.named.publish_lifecycle]
event_kinds = ["resource", "statement"]
min_severity = "warning"
```

SQLBuild owns envelope validation, local queueing, filtering, and bounded dispatch. The project owns
destination credentials, serialization, routes/topics, acknowledgements, retries, retention, and
durability. SQLBuild core does not provide a Kafka or ClickHouse implementation.

## Delivery behavior

- Lifecycle dispatch prioritizes failures and terminal facts, remaining FIFO within equal priority.
- Queue overflow can displace or drop lower-priority records and is reflected in sink accounting.
- A failing or timed-out sink is isolated from command correctness.
- Provider setup and declaration errors fail before execution because the project configuration is
  invalid.
- Providers shared by multiple sinks are set up and torn down once per command.

Use lifecycle facts—not command-output records—to build execution state and timelines.
