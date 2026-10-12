from dataclasses import dataclass


@dataclass(frozen=True)
class PythonBoundaryTestCase:
    description: str
    source_files: dict[str, str]
    policy: str
    expected_messages: tuple[str, ...]
