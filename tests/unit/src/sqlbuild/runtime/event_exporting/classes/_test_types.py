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
    queued_type: str
    incoming_type: str
    expected_delivered: tuple[str, ...]
    expected_dropped: int


@dataclass(frozen=True)
class PriorityQueueTestCase:
    description: str
    event_types: tuple[str, ...]
    expected_delivered: tuple[str, ...]


@dataclass(frozen=True)
class HealthIntervalTestCase:
    description: str
    interval: object
    expected_error: str


@dataclass(frozen=True)
class InterpreterExitTestCase:
    description: str
    script: str
    expected_returncode: int
