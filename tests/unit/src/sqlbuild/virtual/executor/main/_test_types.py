from dataclasses import dataclass


@dataclass(frozen=True)
class VirtualCloneAggregateTestCase:
    description: str
    action: str
    expected_terminal: str
    expected_error_code: str | None
