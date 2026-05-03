from dataclasses import dataclass


@dataclass(frozen=True)
class QueryCliTestCase:
    description: str
    command: tuple[str, ...]
    expected_stdout_fragment: str
    expected_returncode: int = 0
