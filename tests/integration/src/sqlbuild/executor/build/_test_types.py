from dataclasses import dataclass, field

from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.shared.types import ExecutionStatus


@dataclass(frozen=True)
class BuildExecutionTestCase:
    """Test case for build plan execution with a fake project."""

    description: str
    project_files: dict[str, str]
    expected_status: BuildStatus
    expected_success_count: int = 0
    expected_failure_count: int = 0
    expected_skipped_count: int = 0
    setup_sql: tuple[str, ...] = field(default_factory=tuple)
    run_audits: bool = True
    run_tests: bool = True
    fail_fast: bool = False
    allow_snapshot_schema_change: bool = False
    expected_model_statuses: tuple[tuple[str, ExecutionStatus], ...] = field(default_factory=tuple)
    expected_function_statuses: tuple[tuple[str, ExecutionStatus], ...] = field(
        default_factory=tuple
    )
    expected_function_error_fragments: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    expected_model_audit_count: int = 0
    expected_source_audit_count: int = 0
    expected_end_audit_count: int = 0
    expected_test_count: int = 0
    expected_warning_count: int = 0
    query_change_tracking: bool = True
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...] = field(
        default_factory=tuple
    )
    expected_missing_relations: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SnapshotTimestampExecutionTestCase:
    description: str
    model_name: str
    project_files: dict[str, str]
    initial_setup_sql: tuple[str, ...]
    stale_setup_sql: tuple[str, ...]
    changed_setup_sql: tuple[str, ...]
    expected_validity_columns: tuple[str, ...]
    expected_initial_rows: tuple[tuple[object, ...], ...]
    expected_stale_rows: tuple[tuple[object, ...], ...]
    expected_changed_rows: tuple[tuple[object, ...], ...]
    expected_query: str


@dataclass(frozen=True)
class SnapshotHistoricalTimestampExecutionTestCase:
    description: str
    model_name: str
    project_files: dict[str, str]
    initial_setup_sql: tuple[str, ...]
    changed_setup_sql: tuple[str, ...]
    expected_initial_rows: tuple[tuple[object, ...], ...]
    expected_changed_rows: tuple[tuple[object, ...], ...]
    expected_query: str


@dataclass(frozen=True)
class SnapshotCheckExecutionTestCase:
    description: str
    model_name: str
    project_files: dict[str, str]
    initial_setup_sql: tuple[str, ...]
    unchecked_setup_sql: tuple[str, ...]
    checked_setup_sql: tuple[str, ...]
    expected_validity_columns: tuple[str, ...]
    expected_initial_rows: tuple[tuple[object, ...], ...]
    expected_unchecked_rows: tuple[tuple[object, ...], ...]
    expected_checked_rows: tuple[tuple[object, ...], ...]
    expected_query: str


@dataclass(frozen=True)
class SnapshotHistoricalCheckExecutionTestCase:
    description: str
    model_name: str
    project_files: dict[str, str]
    initial_setup_sql: tuple[str, ...]
    changed_setup_sql: tuple[str, ...]
    expected_initial_rows: tuple[tuple[object, ...], ...]
    expected_changed_rows: tuple[tuple[object, ...], ...]
    expected_query: str


@dataclass(frozen=True)
class SnapshotTimestampFailureTestCase:
    description: str
    model_name: str
    project_files: dict[str, str]
    setup_sql: tuple[str, ...]
    expected_error_fragment: str


@dataclass(frozen=True)
class SnapshotCheckFailureTestCase:
    description: str
    model_name: str
    project_files: dict[str, str]
    setup_sql: tuple[str, ...]
    expected_error_fragment: str


@dataclass(frozen=True)
class SnapshotSchemaChangeExecutionTestCase:
    description: str
    initial_project_files: dict[str, str]
    changed_project_files: dict[str, str]
    initial_setup_sql: tuple[str, ...]
    changed_setup_sql: tuple[str, ...]
    expected_status: BuildStatus
    expected_rows: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    expected_error_fragment: str = ""
    allow_snapshot_schema_change: bool = False
    expected_query: str = ""


@dataclass(frozen=True)
class SnapshotHardDeleteExecutionTestCase:
    description: str
    model_name: str
    project_files: dict[str, str]
    initial_setup_sql: tuple[str, ...]
    delete_setup_sql: tuple[str, ...]
    expected_initial_rows: tuple[tuple[object, ...], ...]
    expected_deleted_rows: tuple[tuple[object, ...], ...]
    expected_query: str
