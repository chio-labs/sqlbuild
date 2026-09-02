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
