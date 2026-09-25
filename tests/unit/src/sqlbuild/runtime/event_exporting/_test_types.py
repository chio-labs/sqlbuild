from dataclasses import dataclass


@dataclass(frozen=True)
class SinkApiTestCase:
    description: str
    expected_name: str | None = None


@dataclass(frozen=True)
class EventExportPolicyTestCase:
    description: str
    expected_event_count: int
