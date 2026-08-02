from dataclasses import dataclass, field


@dataclass(frozen=True)
class QueryCliTestCase:
    description: str
    command: tuple[str, ...]
    expected_stdout_fragment: str
    expected_returncode: int = 0


@dataclass(frozen=True)
class QueryFileCliTestCase:
    description: str
    query_file_path: str
    query_sql: str
    expected_stdout_fragment: str


@dataclass(frozen=True)
class QueryFileErrorCliTestCase:
    description: str
    command: tuple[str, ...]
    expected_stderr_fragment: str
    repo_files: dict[str, str] = field(default_factory=dict)
    binary_files: dict[str, bytes] = field(default_factory=dict)
