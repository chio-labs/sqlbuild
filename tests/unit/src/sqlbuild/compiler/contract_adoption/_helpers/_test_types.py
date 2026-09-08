from dataclasses import dataclass


@dataclass(frozen=True)
class DeclaredTypeSpanTestCase:
    description: str
    contents: str
    declared_type: str
    expected_value: str
