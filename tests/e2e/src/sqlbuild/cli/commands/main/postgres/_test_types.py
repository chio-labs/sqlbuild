from dataclasses import dataclass, field


@dataclass(frozen=True)
class PostgresBuildE2ETestCase:
    description: str
    expected_row_count: int
    expected_table_name: str = "fact_orders"
    command: tuple[str, ...] = field(default_factory=tuple)
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_return_code: int = 0


@dataclass(frozen=True)
class PostgresSourceLoaderStrategiesE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_countries: tuple[tuple[object, ...], ...]
    expected_webhook_event_counts: tuple[tuple[object, ...], ...]
    expected_order_events: tuple[tuple[object, ...], ...]
    expected_customers: tuple[tuple[object, ...], ...]
    expected_loader_status: tuple[tuple[object, ...], ...]
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_return_code: int = 0


@dataclass(frozen=True)
class PostgresSourceLoaderDagE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]
    expected_return_code: int = 0


@dataclass(frozen=True)
class PostgresLoaderWaffleShopE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]
    expected_event_count: int
    expected_return_code: int = 0


@dataclass(frozen=True)
class PostgresDiffE2ETestCase:
    description: str
    mutation_sql: tuple[str, ...]
    command: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_return_code: int = 0


@dataclass(frozen=True)
class PostgresSnapshotE2ETestCase:
    description: str
    expected_current_rows_after_initial_build: tuple[tuple[object, ...], ...]
    expected_current_rows_after_recovery: tuple[tuple[object, ...], ...]
    expected_historical_timestamp_rows: tuple[tuple[object, ...], ...]
    expected_historical_check_rows: tuple[tuple[object, ...], ...]
    expected_failure_fragments: tuple[str, ...]


@dataclass(frozen=True)
class PostgresSnapshotApplyE2ETestCase:
    description: str
    expected_current_check_rows: tuple[tuple[object, ...], ...]
    expected_current_delete_rows: tuple[tuple[object, ...], ...]
    expected_historical_timestamp_rows: tuple[tuple[object, ...], ...]
    expected_historical_check_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class PostgresScenarioLocalReplayE2ETestCase:
    description: str
    model_sql: str
    scenario_sql: str
    expected_stdout_fragments: tuple[str, ...]
    expected_return_code: int = 0
    scenario_name: str = "transpilable_event_rollup"
    expected_local_rows: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    local_rows_sql: str = ""
    corrupt_capture_dialect: bool = False
