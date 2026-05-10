from dataclasses import dataclass, field


@dataclass(frozen=True)
class DatabricksCliTestCase:
    description: str
    command: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_return_code: int = 0


@dataclass(frozen=True)
class DatabricksBuildE2ETestCase:
    description: str
    expected_table_name: str
    expected_row_count: int
    expected_fact_order_rows: tuple[tuple[object, ...], ...]
    expected_udf_rows: tuple[tuple[object, ...], ...]
    expected_daily_revenue_rows: tuple[tuple[object, ...], ...]
    command: tuple[str, ...] = field(default_factory=tuple)
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_return_code: int = 0


@dataclass(frozen=True)
class DatabricksDiffE2ETestCase:
    description: str
    mutation_sql: tuple[str, ...]
    command: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_return_code: int = 0


@dataclass(frozen=True)
class DatabricksErrorE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_error_fragment: str
    expected_return_code: int = 1


@dataclass(frozen=True)
class DatabricksScenarioLocalReplayE2ETestCase:
    description: str
    model_sql: str
    scenario_sql: str
    expected_stdout_fragments: tuple[str, ...]
    expected_return_code: int = 0
    scenario_name: str = "transpilable_event_rollup"
    expected_local_rows: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    local_rows_sql: str = ""
