from dataclasses import dataclass


@dataclass(frozen=True)
class EventExporterDispatcherTestCase:
    description: str
    expected_delivered: int


@dataclass(frozen=True)
class EventExporterTeardownTestCase:
    description: str
    expected_teardown_count: int
