from dataclasses import dataclass


@dataclass(frozen=True)
class CommandOutputJsonTestCase:
    description: str
    expected_value: object


@dataclass(frozen=True)
class InvocationContextTestCase:
    description: str
    raw_value: str
    expected_value: object | None = None
    expected_error: str | None = None


@dataclass(frozen=True)
class ReplacementRecordTestCase:
    description: str
    data: bytes
    message: str | None
    expected_message: str


@dataclass(frozen=True)
class InvalidReplacementRecordTestCase:
    description: str
    changes: dict[str, object]
    expected_error: str
