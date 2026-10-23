from dataclasses import dataclass, field


@dataclass(frozen=True)
class SqlServerBuildE2ETestCase:
    description: str
    expected_row_count: int
    expected_table_name: str = "fact_orders"
    command: tuple[str, ...] = field(default_factory=tuple)
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_return_code: int = 0


@dataclass(frozen=True)
class SqlServerCloneE2ETestCase:
    description: str
    expected_stdout_fragments: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]
    expected_return_code: int = 0


@dataclass(frozen=True)
class SqlServerDiffE2ETestCase:
    description: str
    command: tuple[str, ...]
    mutation_sql: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...]
    expected_return_code: int
    expected_absent_stdout_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class SqlServerDbtProfileE2ETestCase:
    description: str
    schema_prefix: str
    expected_toml_fragments: tuple[str, ...]


@dataclass(frozen=True)
class SqlServerSourceLoaderE2ETestCase:
    description: str
    expected_rows: tuple[tuple[str, ...], ...]
    expected_return_code: int = 0
