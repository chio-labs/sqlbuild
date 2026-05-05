from dataclasses import dataclass, field


@dataclass(frozen=True)
class SnowflakeCliTestCase:
    description: str
    command: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_return_code: int = 0
    expected_schema_fragment: str = ""


@dataclass(frozen=True)
class SnowflakeBuildE2ETestCase:
    description: str
    expected_table_name: str
    expected_row_count: int
    expected_udf_rows: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    command: tuple[str, ...] = field(default_factory=tuple)
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_return_code: int = 0


@dataclass(frozen=True)
class SnowflakeDiffE2ETestCase:
    description: str
    mutation_sql: tuple[str, ...]
    command: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_return_code: int = 0
