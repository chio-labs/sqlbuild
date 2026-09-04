from dataclasses import dataclass


@dataclass(frozen=True)
class EventExporterDispatcherTestCase:
    description: str
    expected_delivered: int


@dataclass(frozen=True)
class EventExporterTeardownTestCase:
    description: str
    expected_teardown_count: int


@dataclass(frozen=True)
class SharedSinkProviderTestCase:
    description: str
    expected_delivery_count: int


@dataclass(frozen=True)
class PriorityPairTestCase:
    description: str
    queued_priority: int
    incoming_priority: int
    expected_inserted: bool
    expected_displaced_sequence: int | None
    expected_retained_sequence: int


@dataclass(frozen=True)
class PriorityQueueTestCase:
    description: str
    expected_sequences: tuple[int, ...]


@dataclass(frozen=True)
class HealthIntervalTestCase:
    description: str
    interval: object
    expected_error: str
