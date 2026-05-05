from dataclasses import dataclass, field


@dataclass(frozen=True)
class BigQueryCliTestCase:
    description: str
    command: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_return_code: int = 0


@dataclass(frozen=True)
class BigQueryBuildE2ETestCase:
    description: str
    expected_table_name: str
    expected_row_count: int
    expected_fact_order_rows: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    expected_udf_rows: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    expected_daily_revenue_rows: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    command: tuple[str, ...] = field(default_factory=tuple)
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_return_code: int = 0


@dataclass(frozen=True)
class BigQueryDiffE2ETestCase:
    description: str
    mutation_sql: tuple[str, ...]
    command: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_return_code: int = 0


@dataclass(frozen=True)
class BigQueryModelBuildE2ETestCase:
    description: str
    model_name: str
    expected_sql_fragment: str
    expected_return_code: int = 0


@dataclass(frozen=True)
class BigQueryErrorE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_error_fragment: str
    expected_return_code: int = 1
