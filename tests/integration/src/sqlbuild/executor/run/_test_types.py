from dataclasses import dataclass, field

from sqlbuild.adapter.contract.types import TablePromotionMode
from sqlbuild.executor.contracts.types import ExecutionPhase


@dataclass(frozen=True)
class TableSuccessTestCase:
    """Test case where execution succeeds and target is populated."""

    description: str
    setup_sql: tuple[str, ...]
    model_sql: str
    target_schema: str | None
    target_name: str
    promotion_mode: TablePromotionMode
    expected_row_count: int
    expected_audit_count: int = 0
    type_enforcement: bool = False
    declared_columns: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    pre_hook: object = None
    post_hook: object = None
    audit_sql: str | None = None
    audit_severity: str = "warn"
    extra_audits: tuple[object, ...] = field(default_factory=tuple)
    query_change_tracking: bool = True
    expected_column_names: tuple[str, ...] = field(default_factory=tuple)
    expected_column_types: tuple[str, ...] = field(default_factory=tuple)
    expected_warning_fragment: str | None = None
    hook_functions: tuple[object, ...] = field(default_factory=tuple)
    expected_lifecycle_event_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...] = field(
        default_factory=tuple
    )


@dataclass(frozen=True)
class TableFailureTestCase:
    """Test case where execution fails at a specific phase."""

    description: str
    setup_sql: tuple[str, ...]
    model_sql: str
    target_schema: str | None
    target_name: str
    promotion_mode: TablePromotionMode
    expected_failed_phase: ExecutionPhase
    expected_audit_count: int = 0
    expected_error_fragment: str | None = None
    expected_staging_relation: str | None = None
    expected_promoted_relation: str | None = None
    expected_row_count: int | None = None
    type_enforcement: bool = False
    declared_columns: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    pre_hook: object = None
    post_hook: object = None
    audit_sql: str | None = None
    audit_severity: str = "warn"
    extra_audits: tuple[object, ...] = field(default_factory=tuple)
    hook_functions: tuple[object, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class AuditSqlResolutionTestCase:
    description: str
    unresolved_sql: str
    attached_target_name: str
    resolved_target_name: str
    expected_resolved_sql: str


@dataclass(frozen=True)
class TableReuseExecutionTestCase:
    description: str
    reuse_hard_copy: bool
    promotion_mode: TablePromotionMode
    expected_status: str
    expected_rows: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    expected_error_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_lifecycle_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_target_exists: bool = True


@dataclass(frozen=True)
class TableReuseFailureExecutionTestCase:
    description: str
    setup_sql: tuple[str, ...]
    fingerprint_version_hash: str
    expected_status: str
    expected_failed_phase: ExecutionPhase
    expected_error_fragments: tuple[str, ...]
    expected_target_exists: bool


@dataclass(frozen=True)
class TableReuseAuditProofExecutionTestCase:
    description: str
    expected_status: str
    expected_rows: tuple[tuple[object, ...], ...]
    expected_audit_count: int
    expected_reused_count: int
    expected_metadata_reused: bool


@dataclass(frozen=True)
class SnapshotReuseExecutionTestCase:
    description: str
    expected_status: str
    expected_rows: tuple[tuple[object, ...], ...]
    expected_lifecycle_fragments: tuple[str, ...]
    expected_seed_exists: bool


@dataclass(frozen=True)
class SnapshotReuseFailureExecutionTestCase:
    description: str
    fingerprint_version_hash: str
    expected_status: str
    expected_error_fragment: str
    expected_target_exists: bool


@dataclass(frozen=True)
class SnapshotReuseVariantExecutionTestCase:
    description: str
    reuse_hard_copy: bool
    expected_status: str
    expected_rows: tuple[tuple[object, ...], ...]
    expected_lifecycle_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_audit_count: int = 0
