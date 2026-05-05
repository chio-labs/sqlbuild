from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectLocalAdapterCliTestCase:
    description: str
    command: tuple[str, ...]
    expected_stdout_fragment: str
    expected_return_code: int = 0
