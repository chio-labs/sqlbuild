from dataclasses import dataclass


@dataclass(frozen=True)
class EventExporterDecoratorTestCase:
    description: str
    expected_name: str


@dataclass(frozen=True)
class InvalidEventExporterNameTestCase:
    description: str
    name: str
    expected_error: str


@dataclass(frozen=True)
class SinkApiTestCase:
    description: str
    expected_name: str | None = None


@dataclass(frozen=True)
class EventExporterFilterTestCase:
    description: str
    event_kinds: object
    min_severity: str
    expected_error: str | None = None
    expected_kinds: frozenset[str] | None = None


@dataclass(frozen=True)
class EventExportPolicyTestCase:
    description: str
    expected_event_count: int
