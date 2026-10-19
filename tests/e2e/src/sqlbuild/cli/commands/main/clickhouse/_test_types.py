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


@dataclass(frozen=True)
class ClickHousePhysicalLayoutE2ETestCase:
    description: str
    first_events: str
    later_events: str
    expected_create_fragments: tuple[str, ...]
    expected_partition_rewrites: dict[str, bool]
    expected_totals: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class ClickHouseLayoutChangeE2ETestCase:
    description: str
    first_partition_by: str
    changed_partition_by: str
    full_refresh_args: tuple[str, ...]
    expected_warning_codes: tuple[str, ...]
    expected_full_refresh_warning_codes: tuple[str, ...]
    expected_rebuilt_fragment: str


@dataclass(frozen=True)
class ClickHouseNullabilityE2ETestCase:
    description: str
    model_sql: str
    edited_select: str
    expected_return_code: int
    expected_output_fragment: str
    expected_rows: tuple[tuple[object, ...], ...]
    expected_types: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class ClickHouseWaffleShopE2ETestCase:
    description: str
    expected_return_codes: tuple[int, int, int]
    expected_summary_fragments: tuple[str, str, str]
    expected_row_counts: dict[str, int]


@dataclass(frozen=True)
class ClickHouseOutputColumnNameE2ETestCase:
    description: str
    selected_order_id: str
    expected_return_code: int
    expected_output_fragments: tuple[str, ...]
    expected_columns: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class ClickHouseRecallRetentionTestCase:
    description: str
    recall_settings: str
    expected_ttl_days: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class ClickHouseRecallExpiryTestCase:
    description: str
    created_with: str
    recall_settings: str
    aged_days: int
    expected_fix_statements: int


@dataclass(frozen=True)
class ClickHouseRecallDuplicateTestCase:
    description: str
    view_counts_sql: str
    expected_physical_factor: int


@dataclass(frozen=True)
class ClickHouseRecallPermissionTestCase:
    description: str
    connection_settings: str
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class ClickHouseRecallConcurrencyTestCase:
    description: str
    targets: tuple[str, ...]
    expected_status: str


@dataclass(frozen=True)
class ClickHouseRecallAbandonedTestCase:
    description: str
    heartbeat_seconds: str
    expected_status: str


@dataclass(frozen=True)
class ClickHouseRecallOutputTestCase:
    description: str
    args: tuple[str, ...]
    expected_stream: str


@dataclass(frozen=True)
class ClickHouseRecallRetentionConflictTestCase:
    description: str
    created_with: str
    built_with: str
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class ClickHouseRecallLimitedWriterTestCase:
    description: str
    between_builds: tuple[str, ...]
    expected_recorded: list[list[object]]


@dataclass(frozen=True)
class ClickHouseRecallPartialInsertTestCase:
    description: str
    revoked_inserts: tuple[str, ...]
    expected_delivery: list[list[object]]
