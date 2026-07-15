from dataclasses import dataclass, field

from sqlbuild.compiler.auditing.types import AuditRunScope
from sqlbuild.compiler.planner.types import OnSchemaChange
from sqlbuild.executor.run.types import ExecutionPhase
from sqlbuild.executor.scheduling.types import ExecutionStatus


@dataclass(frozen=True)
class IncrementalSuccessTestCase:
    """Test case where incremental execution succeeds."""

    description: str
    setup_sql: tuple[str, ...]
    model_sql: str
    target_schema: str | None
    target_name: str
    incremental_strategy: str
    expected_row_count: int
    expected_status: ExecutionStatus = ExecutionStatus.SUCCESS
    unique_key: tuple[str, ...] = field(default_factory=tuple)
    on_schema_change: OnSchemaChange | None = None
    cursor_column: str | None = None
    cursor_type: str | None = None
    cursor_grain: str | None = None
    cursor_start: str | None = None
    cursor_end: str | None = None
    cursor_input_relations: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    cursor_inputs_model_backed: bool = False
    type_enforcement: bool = False
    declared_columns: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    pre_hook: object = None
    post_hook: object = None
    audit_sql: str | None = None
    audit_severity: str = "warn"
    audit_run_scope: AuditRunScope = AuditRunScope.FINAL
    query_change_tracking: bool = True
    expected_audit_count: int = 0
    expected_warning_count: int = 0
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...] = field(
        default_factory=tuple
    )
    expected_column_names: tuple[str, ...] = field(default_factory=tuple)
    expected_delta_cleaned: bool = True
    hook_functions: tuple[object, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class IncrementalFailureTestCase:
    """Test case where incremental execution fails at a specific phase."""

    description: str
    setup_sql: tuple[str, ...]
    model_sql: str
    target_schema: str | None
    target_name: str
    incremental_strategy: str
    expected_failed_phase: ExecutionPhase
    unique_key: tuple[str, ...] = field(default_factory=tuple)
    on_schema_change: OnSchemaChange | None = None
    cursor_column: str | None = None
    cursor_type: str | None = None
    cursor_grain: str | None = None
    cursor_start: str | None = None
    cursor_end: str | None = None
    cursor_input_relations: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    cursor_inputs_model_backed: bool = False
    type_enforcement: bool = False
    declared_columns: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    pre_hook: object = None
    post_hook: object = None
    audit_sql: str | None = None
    audit_severity: str = "error"
    audit_run_scope: AuditRunScope = AuditRunScope.FINAL
    expected_audit_count: int = 0
    expected_error_fragment: str | None = None
    expected_staging_relation: str | None = None
    expected_promoted_relation: str | None = None
    expected_row_count: int | None = None
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...] = field(
        default_factory=tuple
    )
    hook_functions: tuple[object, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class IncrementalSeedReuseTestCase:
    description: str
    origin_sql: str
    input_sql: str
    model_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    reuse_hard_copy: bool = True
    expected_lifecycle_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class IncrementalSeedReuseFailureTestCase:
    description: str
    origin_sql: str
    input_sql: str
    model_sql: str
    fingerprint_version_hash: str
    expected_status: ExecutionStatus
    expected_failed_phase: ExecutionPhase
    expected_error_fragments: tuple[str, ...]
    expected_target_exists: bool
