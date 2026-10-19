from dataclasses import dataclass


@dataclass(frozen=True)
class ClickHouseBuildE2ETestCase:
    description: str
    expected_customer_rows: tuple[tuple[object, ...], ...]
    expected_order_totals: tuple[tuple[object, ...], ...]
    expected_name_rows: tuple[tuple[object, ...], ...]
    expected_daily_rows_after_first_build: tuple[tuple[object, ...], ...]
    expected_daily_rows_after_second_build: tuple[tuple[object, ...], ...]
    expected_latest_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class ClickHouseSnapshotE2ETestCase:
    description: str
    expected_current_rows_after_initial_build: tuple[tuple[object, ...], ...]
    expected_current_rows_after_recovery: tuple[tuple[object, ...], ...]
    expected_historical_timestamp_rows: tuple[tuple[object, ...], ...]
    expected_historical_check_rows: tuple[tuple[object, ...], ...]
    expected_failure_fragments: tuple[str, ...]


@dataclass(frozen=True)
class ClickHouseSnapshotApplyE2ETestCase:
    description: str
    expected_current_check_rows: tuple[tuple[object, ...], ...]
    expected_current_delete_rows: tuple[tuple[object, ...], ...]
    expected_historical_timestamp_rows: tuple[tuple[object, ...], ...]
    expected_historical_check_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class ClickHouseDiffE2ETestCase:
    description: str
    command: tuple[str, ...]
    mutation_sql: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...]
    expected_return_code: int
    expected_absent_stdout_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class ClickHouseCloneE2ETestCase:
    description: str
    expected_stdout_fragments: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]
