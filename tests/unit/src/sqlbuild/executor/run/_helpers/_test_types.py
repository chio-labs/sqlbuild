from dataclasses import dataclass, field
from datetime import datetime

from sqlbuild.adapter.contract.models import ColumnInfo, LifeCycleEvent
from sqlbuild.executor.run.types import AuditGateReuseReason, AuditGateStatus, ExecutionPhase


@dataclass(frozen=True)
class RuntimeCursorSpecBoundaryTestCase:
    description: str
    expected_grain: str
    expected_start: str
    expected_end: str


@dataclass(frozen=True)
class LifecycleProgressTestCase:
    description: str
    expected_event_types: tuple[str, ...]


@dataclass(frozen=True)
class PromotionProgressTestCase:
    description: str
    strategy: str
    expected_method: str
    expected_event_types: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeFutureCursorTestCase:
    description: str
    expected_start: str
    expected_end: str
    expected_error_fragment: str | None = None
    expected_determining_relation: str | None = None


@dataclass(frozen=True)
class CursorSentinelSubstitutionErrorTestCase:
    description: str
    sql: str
    expected_error_fragment: str


@dataclass(frozen=True, kw_only=True)
class CursorSentinelSubstitutionTestCase:
    description: str
    start: str
    end: str
    sql: str
    expected_sql: str


@dataclass(frozen=True)
class BuildQualifiedNameTestCase:
    description: str
    adapter_name: str
    database: str | None
    schema: str | None
    name: str
    expected_qualified: str


@dataclass(frozen=True)
class InclusiveEndBatchWindowTestCase:
    description: str
    start: str
    inclusive_end: str
    batch_size: str
    cursor_type: str
    cursor_grain: str | None
    expected_batch_count: int
    expected_final_window_end: str
    expected_final_value_included: bool


@dataclass(frozen=True)
class BuildFailedResultTestCase:
    description: str
    error: str | BaseException
    recorded_statements: tuple[str, ...]
    warning_messages: tuple[str, ...]
    expected_model_name: str
    expected_error_message: str
    expected_error_code: str
    expected_lifecycle_events: tuple[LifeCycleEvent, ...]


@dataclass(frozen=True)
class RuntimeCursorStartTestCase:
    description: str
    target_max: object | None
    upstream_min: object
    upstream_max: object
    cursor_type: str
    warehouse_column_type: str
    cursor_start: str | None
    expected_start: str
    expected_end: str


@dataclass(frozen=True)
class RuntimeCursorEndBoundTestCase:
    description: str
    upstream_min: object
    upstream_max: object
    cursor_type: str
    cursor_grain: str | None
    warehouse_column_type: str
    expected_start: str
    expected_end: str


@dataclass(frozen=True)
class RuntimeCursorOverrideTestCase:
    description: str
    upstream_min: object
    upstream_max: object
    cursor_type: str
    cursor_grain: str | None
    warehouse_column_type: str
    start_cursor_override: str | None
    end_cursor_override: str | None
    expected_start: str
    expected_end: str


@dataclass(frozen=True)
class AuthoritativeRuntimeCursorOverrideTestCase:
    description: str
    cursor_type: str
    cursor_grain: str | None
    start_cursor_override: str
    end_cursor_override: str
    expected_bounds: object


@dataclass(frozen=True)
class RuntimeExistingTargetOverrideTestCase:
    description: str
    upstream_min: object
    upstream_max: object
    target_max: object
    cursor_type: str
    cursor_grain: str | None
    cursor_start: str | None
    start_cursor_override: str
    end_cursor_override: str
    warehouse_column_type: str
    expected_bounds: object


@dataclass(frozen=True)
class ReportedRowsAffectedTestCase:
    description: str
    total_rows: int
    row_count_known: bool
    expected_rows_affected: int | None


@dataclass(frozen=True)
class MicrobatchCursorDiscoveryTestCase:
    description: str
    warehouse_column_type: str
    cursor_min: object
    cursor_max: object
    cursor_type: str
    expected_start: str
    expected_end: str


@dataclass(frozen=True)
class MicrobatchCursorDiscoveryFailureTestCase:
    description: str
    warehouse_column_type: str
    cursor_min: object
    cursor_max: object
    expected_error_fragment: str


@dataclass(frozen=True)
class RuntimeTargetMaxTestCase:
    description: str
    target_rows: tuple[object, ...]
    upstream_min: object
    upstream_max: object
    cursor_type: str
    expected_start: str
    expected_end: str


@dataclass(frozen=True)
class RuntimeTargetProbeFailureTestCase:
    description: str
    expected_error_type: type[BaseException]


@dataclass(frozen=True)
class RuntimeWatermarkStatementTestCase:
    description: str
    target_exists: bool
    expected_statements: tuple[str, ...]
    expected_bounds: object


@dataclass(frozen=True, kw_only=True)
class RuntimeIntegerWatermarkModeTestCase:
    """Runtime integer aggregation case with non-lexicographic values."""

    description: str
    mode: str
    values: tuple[int, int]
    expected_bounds: object


@dataclass(frozen=True)
class MixedTemporalWatermarkTestCase:
    description: str
    expected_start: str
    expected_end: str


@dataclass(frozen=True)
class RuntimeCursorPolicyTestCase:
    description: str
    expected_bounds: object
    lookback: str | None = None
    backfill_duration: str | None = None
    read_destination_cursor: bool = True
    slow_input_setup_sql: str = "INSERT INTO slow_input VALUES (20), (100)"


@dataclass(frozen=True)
class RuntimeCursorFailureTestCase:
    description: str
    slow_input_setup_sql: str
    expected_error_fragment: str


@dataclass(frozen=True)
class SnapshotAdapterRenderingTestCase:
    description: str
    expected_rendered_marker: str


@dataclass(frozen=True)
class AuditGateMetadataSchemaTestCase:
    description: str
    expected_serialized: str


@dataclass(frozen=True)
class AuditGateMetadataFailureTestCase:
    description: str
    metadata_json: str
    expected_diagnostic: str


@dataclass(frozen=True)
class SnapshotLifecycleTestCase:
    description: str
    run_id: str
    pre_hook: tuple[object, ...]
    post_hook: tuple[object, ...]
    expected_hook_events: tuple[str, ...]
    expected_model_name: str
    expected_target_name: str
    hook_functions: tuple[object, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SnapshotHookFailureTestCase:
    description: str
    pre_hooks: object
    post_hooks: object
    expected_phase: ExecutionPhase
    expected_error_fragment: str


@dataclass(frozen=True)
class RenderHooksTestCase:
    description: str
    hooks: object
    expected_statements: tuple[str, ...]


@dataclass(frozen=True)
class PublicHookContextExportTestCase:
    description: str
    expected_export_name: str


@dataclass(frozen=True)
class ExecuteHooksTestCase:
    description: str
    hooks: object
    expected_rows: tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class PythonHookExecutionTestCase:
    description: str
    hooks: object
    expected_error_fragment: str


@dataclass(frozen=True)
class PythonHookInvocationTestCase:
    description: str
    expected_message: str
    expected_rows: list[tuple[object, ...]]
    expected_model_name: str
    expected_phase: str
    expected_hook_name: str
    expected_hook_index: int
    expected_run_id: str
    expected_target: str
    expected_vars: dict[str, object]
    expected_destination_name: str
    expected_destination_schema: str
    expected_adapter_name: str
    expected_recorded_events: tuple[str, ...]


@dataclass(frozen=True)
class PermanentRequirementTestCase:
    description: str
    source_created_at: datetime
    expected_operation_kind: str
    expected_retention_days: int


@dataclass(frozen=True)
class PermanentPromotionTestCase:
    description: str
    initial_state: str
    operation_identity: str
    expected_timeline: tuple[str, ...]
    expected_completion_time: datetime | None


@dataclass(frozen=True)
class PermanentArchiveConflictTestCase:
    description: str
    archive_generation_offset_seconds: int
    expected_error_fragment: str


@dataclass(frozen=True)
class PermanentPersistedConflictTestCase:
    description: str
    expected_error_fragment: str


@dataclass(frozen=True)
class PermanentIdentifierFitTestCase:
    description: str
    identifier_limit: int
    expected_prefix: str


@dataclass(frozen=True)
class PythonHookSkipTestCase:
    description: str
    expected_skipped: bool
    expected_status: str
    expected_skip_reason: str
    expected_skip_mode: str = "soft"
    hook_phase: str = "pre_hooks"


@dataclass(frozen=True)
class PythonHookContextParameterTestCase:
    description: str
    hook_name: str
    expected_context_count: int
    expected_return_ignored: object


@dataclass(frozen=True)
class PythonHookRuntimeErrorTestCase:
    description: str
    expected_error_fragment: str


@dataclass(frozen=True)
class PythonHookInvalidReturnTestCase:
    description: str
    returned: object
    expected_error_fragment: str


@dataclass(frozen=True)
class SnapshotRuntimeContractErrorTestCase:
    description: str
    contract_columns: tuple[ColumnInfo, ...]
    run_id: str
    expected_error_fragment: str


@dataclass(frozen=True)
class SnapshotSchemaChangeTestCase:
    description: str
    target_columns: tuple[ColumnInfo, ...]
    delta_columns: tuple[ColumnInfo, ...]
    expected_valid: bool
    expected_error_fragment: str | None = None


@dataclass(frozen=True)
class FingerprintAuditGateMetadataTestCase:
    description: str
    audit_outcome: str
    expected_status: AuditGateStatus
    expected_result_count: int
    expected_existing_field: str


@dataclass(frozen=True)
class FingerprintAuditGateNoAuditsTestCase:
    description: str
    expected_existing_field: str


@dataclass(frozen=True)
class FingerprintAuditGateEdgeTestCase:
    description: str
    plan_severity: str
    result_outcome: str
    result_audit_name: str
    result_column_name: str | None
    expected_status: AuditGateStatus
    expected_result_count: int


@dataclass(frozen=True)
class TryWriteFingerprintAuditGateTestCase:
    description: str
    expected_status: AuditGateStatus
    expected_result_count: int


@dataclass(frozen=True)
class AuditGateReuseDecisionTestCase:
    description: str
    metadata_mode: str
    status: AuditGateStatus
    planned_attached_column_name: str | None
    planned_resolved_sql: str
    expected_reusable: bool
    expected_reason: AuditGateReuseReason
    expected_reusable_count: int
    expected_missing_count: int
    planned_always_run: bool = False


@dataclass(frozen=True)
class AuditGatePartialReuseDecisionTestCase:
    description: str
    changed_resolved_sql: str
    expected_reusable: bool
    expected_reason: AuditGateReuseReason
    expected_reusable_count: int
    expected_missing_count: int


@dataclass(frozen=True)
class ReuseFromAuditGateDecisionTestCase:
    description: str
    origin_unresolved_sql: str
    origin_resolved_sql: str
    planned_unresolved_sql: str
    planned_resolved_sql: str
    severity: str
    expected_reusable: bool
    expected_reason: AuditGateReuseReason
    expected_reusable_count: int
    expected_missing_count: int
    planned_always_run: bool = False


@dataclass(frozen=True)
class RuntimeContractValidationTestCase:
    description: str
    contract_enforced: bool
    contract_columns: tuple[ColumnInfo, ...]
    actual_columns: tuple[ColumnInfo, ...]
    expected_valid: bool
    expected_error_fragment: str | None = None
    expected_error_code: str | None = None
