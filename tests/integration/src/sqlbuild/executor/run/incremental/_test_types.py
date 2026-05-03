from dataclasses import dataclass, field

from sqlbuild.compiler.auditing.types import AuditRunScope
from sqlbuild.compiler.planner.types import OnSchemaChange
from sqlbuild.executor.shared.types import ExecutionPhase, ExecutionStatus


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
    type_enforcement: bool = False
    declared_columns: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    pre_hook: object = None
    post_hook: object = None
    audit_sql: str | None = None
    audit_severity: str = "warn"
    audit_run_scope: AuditRunScope = AuditRunScope.FINAL
    fingerprint_schema: str | None = None
    expected_audit_count: int = 0
    expected_warning_count: int = 0
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...] = field(
        default_factory=tuple
    )
    expected_column_names: tuple[str, ...] = field(default_factory=tuple)
    expected_delta_cleaned: bool = True


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
