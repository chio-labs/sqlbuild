from dataclasses import dataclass, field

from sqlbuild.compiler.auditing.types import AuditRunScope
from sqlbuild.compiler.planner.types import OnSchemaChange
from sqlbuild.executor.shared.types import ExecutionPhase, ExecutionStatus


@dataclass(frozen=True)
class MicrobatchSuccessTestCase:
    """Test case where microbatch execution succeeds."""

    description: str
    setup_sql: tuple[str, ...]
    model_sql: str
    target_schema: str | None
    target_name: str
    incremental_strategy: str
    cursor_column: str
    cursor_type: str
    batch_size: str
    microbatch_start: str
    microbatch_end: str
    expected_row_count: int
    expected_status: ExecutionStatus = ExecutionStatus.SUCCESS
    cursor_input_relations: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    unique_key: tuple[str, ...] = field(default_factory=tuple)
    on_schema_change: OnSchemaChange | None = None
    is_full_refresh: bool = False
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
    expected_executed_statement_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MicrobatchFailureTestCase:
    """Test case where microbatch execution fails."""

    description: str
    setup_sql: tuple[str, ...]
    model_sql: str
    target_schema: str | None
    target_name: str
    incremental_strategy: str
    cursor_column: str
    cursor_type: str
    batch_size: str
    microbatch_start: str
    microbatch_end: str
    expected_failed_phase: ExecutionPhase
    cursor_input_relations: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    unique_key: tuple[str, ...] = field(default_factory=tuple)
    on_schema_change: OnSchemaChange | None = None
    is_full_refresh: bool = False
    pre_hook: object = None
    post_hook: object = None
    audit_sql: str | None = None
    audit_severity: str = "error"
    audit_run_scope: AuditRunScope = AuditRunScope.FINAL
    expected_audit_count: int = 0
    expected_error_fragment: str | None = None
    expected_row_count: int | None = None
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...] = field(
        default_factory=tuple
    )
    expected_delta_retained: bool = False
