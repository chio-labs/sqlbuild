from dataclasses import dataclass, field

Rows = tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class LoaderStrategiesTestCase:
    description: str
    command: tuple[str, ...]
    expected_countries: Rows
    expected_webhook_event_counts: Rows
    expected_order_events: Rows
    expected_customers: Rows
    expected_loader_status: Rows
    expected_stdout_fragments: tuple[str, ...]
    expected_return_code: int = 0


@dataclass(frozen=True)
class LoaderRowsTestCase:
    description: str
    command: tuple[str, ...]
    expected_rows: Rows
    expected_return_code: int = 0


@dataclass(frozen=True)
class LoaderWaffleShopTestCase:
    description: str
    command: tuple[str, ...]
    expected_rows: Rows
    expected_stdout_fragments: tuple[str, ...]
    expected_event_count: int
    expected_return_code: int = 0


@dataclass(frozen=True)
class IntermediateDagStrategyTestCase:
    description: str
    loader_py: str
    expected_intermediate_rows: Rows
    expected_terminal_rows: Rows
    command: tuple[str, ...] = ("--no-color", "load", "--select", "+raw_events")
    expected_return_code: int = 0


@dataclass(frozen=True)
class DltLoadTestCase:
    description: str
    expected_loaded_rows: Rows
    expected_model_rows: Rows
    expected_return_code: int = 0


@dataclass(frozen=True)
class SourceDeferralTestCase:
    description: str
    expected_model_rows: Rows
    expected_loader_rows: Rows
    command: tuple[str, ...] = ("--no-color", "build", "--select", "stg_orders")
    expected_return_code: int = 0


@dataclass(frozen=True)
class SnapshotTestCase:
    description: str
    expected_current_rows_after_initial_build: Rows
    expected_current_rows_after_recovery: Rows
    expected_historical_timestamp_rows: Rows
    expected_historical_check_rows: Rows
    expected_failure_fragments: tuple[str, ...]


@dataclass(frozen=True)
class SnapshotApplyTestCase:
    """Current-snapshot rows carry ``True``/``False`` open-version flags, rendered per warehouse."""

    description: str
    expected_current_check_rows: tuple[tuple[str, str, bool], ...]
    expected_current_delete_rows: tuple[tuple[str, str, bool], ...]
    expected_historical_timestamp_rows: Rows
    expected_historical_check_rows: Rows


@dataclass(frozen=True)
class NodeResultTestCase:
    description: str
    expected_rows: Rows
    expected_return_code: int = 0


@dataclass(frozen=True)
class CliTestCase:
    description: str
    command: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_return_code: int = 0


@dataclass(frozen=True)
class ScenarioLocalReplayTestCase:
    description: str
    model_sql: str
    scenario_sql: str
    expected_stdout_fragments: tuple[str, ...]
    expected_return_code: int = 0
    scenario_name: str = "transpilable_event_rollup"
    expected_local_rows: Rows = field(default_factory=tuple)
    local_rows_sql: str = ""
    corrupt_capture_dialect: bool = False


@dataclass(frozen=True)
class ScenarioRemoteTestCase:
    description: str
    expected_stdout_fragments: tuple[str, ...]
    expected_retained_suffix_counts: dict[str, int]
    expected_row_counts_by_suffix: dict[str, int]
