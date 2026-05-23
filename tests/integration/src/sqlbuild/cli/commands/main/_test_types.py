from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.planner.models import CursorOverrides


@dataclass(frozen=True)
class LoadCommandIntegrationTestCase:
    description: str
    project_files: dict[str, str]
    expected_exit_code: int
    expected_rows: tuple[tuple[object, ...], ...]
    expected_stdout_fragment: str
    expected_stdout_fragments: tuple[str, ...] = ()
    expected_stdout_absent_fragments: tuple[str, ...] = ()
    expected_json_staging_relation: str | None = None
    expected_json_rows_loaded: int = 0
    expected_lifecycle_sql_fragments: tuple[str, ...] = ()
    select: tuple[str, ...] = ()
    cli_vars: dict[str, object] | None = None


@dataclass(frozen=True)
class LoadCommandSelectionErrorTestCase:
    description: str
    project_files: dict[str, str]
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    expected_error_fragment: str


@dataclass(frozen=True)
class LoadCommandEmptySelectionTestCase:
    description: str
    project_files: dict[str, str]
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    expected_exit_code: int
    expected_stdout_fragment: str
    expected_stdout_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class LoadCommandConcurrencyTestCase:
    description: str
    project_files: dict[str, str]
    max_concurrency: int
    expected_connection_count: int
    expected_source_order: tuple[str, ...]
    expected_json_asset_order: tuple[str, ...]


@dataclass(frozen=True)
class LoadCommandInferredColumnsTestCase:
    description: str
    project_files: dict[str, str]
    expected_row: tuple[object, ...]
    expected_column_types: dict[str, str]


@dataclass(frozen=True)
class LoadCommandMultipleYieldTestCase:
    description: str
    project_files: dict[str, str]
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class LoadCommandBatchedYieldTestCase:
    description: str
    project_files: dict[str, str]
    expected_rows: tuple[tuple[object, ...], ...]
    expected_column_types: dict[str, str]
    expected_lifecycle_sql_fragments: tuple[str, ...]


@dataclass(frozen=True)
class LoadCommandBatchedRowsTestCase:
    description: str
    project_files: dict[str, str]
    select_sql: str
    table_name: str
    expected_rows: tuple[tuple[object, ...], ...]
    expected_column_types: dict[str, str]
    expected_rows_loaded: int
    expected_lifecycle_sql_fragments: tuple[str, ...] = ()
    absent_lifecycle_sql_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class LoadCommandLifecycleOrderTestCase:
    description: str
    project_files: dict[str, str]
    expected_lifecycle_sql_order: tuple[str, ...]


@dataclass(frozen=True)
class LoadCommandWriteStrategyTestCase:
    description: str
    project_files: dict[str, str]
    select_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    run_count: int = 2


@dataclass(frozen=True)
class LoadCommandWriteStrategyLifecycleTestCase:
    description: str
    project_files: dict[str, str]
    expected_first_run_fragments: tuple[str, ...]
    expected_second_run_fragments: tuple[str, ...]
    absent_second_run_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class LoadCommandCursorNoneTestCase:
    description: str
    project_files: dict[str, str]
    select_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    run_count: int = 2
    setup_sql: tuple[str, ...] = ()


@dataclass(frozen=True)
class LoadCommandLifecycleSqlTestCase:
    description: str
    project_files: dict[str, str]
    run_count: int
    expected_lifecycle_sql_fragments: tuple[str, ...] = ()
    absent_lifecycle_sql_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class LoadCommandAdapterCallTestCase:
    description: str
    project_files: dict[str, str]
    method_name: str
    expected_sql: str
    expected_unique_key: tuple[str, ...] = ()


@dataclass(frozen=True)
class LoadCommandReloadContextTestCase:
    description: str
    project_files: dict[str, str]
    reload: bool
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class LoadCommandCursorOverrideContextTestCase:
    description: str
    project_files: dict[str, str]
    cursor_overrides: CursorOverrides | None
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class LoadCommandEmptyRowsTestCase:
    description: str
    project_files: dict[str, str]
    expected_column_types: dict[str, str]


@dataclass(frozen=True)
class LoadCommandFailureTestCase:
    description: str
    project_files: dict[str, str]
    expected_exit_code: int
    expected_stdout_fragment: str


@dataclass(frozen=True)
class LoadCommandFailureCleanupTestCase:
    description: str
    project_files: dict[str, str]
    staging_table_name: str
    expected_staging_exists: bool
    setup_sql: tuple[str, ...] = ()
    target_select_sql: str | None = None
    expected_target_rows: tuple[tuple[object, ...], ...] = ()


@dataclass(frozen=True)
class BuildRunAutoLoadTestCase:
    description: str
    command: str
    expected_stdout_fragments: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class SourceDeferralBuildTestCase:
    description: str
    command: str
    project_files: dict[str, str]
    defer_sources_to: str | None
    setup_sql: tuple[str, ...]
    expected_model_rows: tuple[tuple[object, ...], ...]
    expected_loaded_source_rows: tuple[tuple[object, ...], ...]
    expected_exit_code: int = 0


@dataclass(frozen=True)
class SourceDeferralErrorTestCase:
    description: str
    project_files: dict[str, str]
    expected_error_fragment: str
    defer_sources_to: str | None = None
    select: tuple[str, ...] = ("stg_orders",)


@dataclass(frozen=True)
class SourceDeferralNoErrorTestCase:
    description: str
    project_files: dict[str, str]
    setup_sql: tuple[str, ...]
    select: tuple[str, ...]
    result_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    expected_exit_code: int = 0
    defer_sources_to: str | None = None
    command: str = "build"
    load_sources: bool | None = None


@dataclass(frozen=True)
class SourceDeferralArtifactTestCase:
    description: str
    command: str
    project_files: dict[str, str]
    setup_sql: tuple[str, ...]
    select: tuple[str, ...]
    compiled_relative_paths: tuple[str, ...]
    runtime_relative_paths: tuple[str, ...]
    expected_sql_fragments: tuple[str, ...]
    unexpected_sql_fragments: tuple[str, ...] = ()
    defer_sources_to: str | None = None


@dataclass(frozen=True)
class BuildRunAutoLoadFlagTestCase:
    description: str
    command: str
    project_files: dict[str, str]
    args: tuple[str, ...]
    setup_sql: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]
    expected_stdout_fragments: tuple[str, ...] = ()
    expected_stdout_absent_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class BuildRunAutoLoadSelectionTestCase:
    description: str
    args: tuple[str, ...]
    setup_sql: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]
    expected_stdout_fragments: tuple[str, ...] = ()
    expected_stdout_absent_fragments: tuple[str, ...] = ()
    project_files: dict[str, str] | None = None
    result_table: str = "fact_orders"


@dataclass(frozen=True)
class BuildRunAutoLoadFailureTestCase:
    description: str
    project_files: dict[str, str]
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...]
    expected_model_exists: bool


@dataclass(frozen=True)
class BuildRunAutoLoadJsonTestCase:
    description: str
    project_files: dict[str, str]
    expected_exit_code: int
    expected_source_asset: dict[str, object]


@dataclass(frozen=True)
class PlanAutoLoadOutputTestCase:
    description: str
    project_files: dict[str, str]
    load_sources: bool | None
    expected_stdout_fragments: tuple[str, ...]
    expected_stdout_absent_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlanAutoLoadJsonTestCase:
    description: str
    project_files: dict[str, str]
    load_sources: bool | None
    expected_source_loads: tuple[dict[str, object], ...]
    expected_selected_count: int
    expected_source_load_count: int
