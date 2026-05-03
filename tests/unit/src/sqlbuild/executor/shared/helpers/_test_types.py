from dataclasses import dataclass


@dataclass(frozen=True)
class StatementRecorderTestCase:
    description: str
    statements: tuple[str, ...]
    expected_snapshot: tuple[str, ...]
