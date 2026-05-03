from dataclasses import dataclass


@dataclass(frozen=True)
class MainTestCase:
    description: str
    argv: list[str]
    expected_exit_code: int
