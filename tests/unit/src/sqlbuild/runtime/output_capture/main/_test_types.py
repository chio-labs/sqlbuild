from dataclasses import dataclass


@dataclass(frozen=True)
class CommandOutputJsonTestCase:
    description: str
    expected_value: object
