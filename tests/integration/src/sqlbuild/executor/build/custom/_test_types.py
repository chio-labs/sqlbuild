from dataclasses import dataclass, field

from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.compiler.planner.types import PlanReason
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.shared.types import ExecutionPhase, ExecutionStatus


@dataclass(frozen=True)
class CustomSuccessTestCase:
    description: str
    model_sql: str
    expected_status: ExecutionStatus
    expected_row_count: int
    fn_name: str


@dataclass(frozen=True)
class CustomFailureTestCase:
    description: str
    model_sql: str
    expected_status: ExecutionStatus
    expected_failed_phase: ExecutionPhase
    expected_error_fragment: str
    fn_name: str


@dataclass(frozen=True)
class HookTestCase:
    description: str
    pre_hook: object
    post_hook: object
    expected_status: ExecutionStatus
    expected_table_exists: bool
    expected_failed_phase: ExecutionPhase | None = None


@dataclass(frozen=True)
class FrameworkAuditTestCase:
    description: str
    audit_passes: bool
    expected_status: ExecutionStatus
    expected_audit_count: int
    expected_failed_phase: ExecutionPhase | None = None


@dataclass(frozen=True)
class UserAuditTestCase:
    description: str
    audit_passes: bool
    expected_status: ExecutionStatus
    expected_audit_count: int
    expected_audit_outcome: AuditOutcome


@dataclass(frozen=True)
class CleanupTestCase:
    description: str
    user_fails: bool
    expected_staging_exists: bool


@dataclass(frozen=True)
class ContextVerificationTestCase:
    description: str
    reason: PlanReason
    custom_config: dict[str, object]
    custom_placeholders: dict[str, str]
    environment: str
    effective_vars: dict[str, str]
    expected_is_first_run: bool
    expected_is_full_refresh: bool
    expected_query_changed: bool
    expected_config_key: str
    expected_config_value: object
    expected_placeholder_key: str
    expected_placeholder_value: str
    expected_environment: str
    expected_var_key: str
    expected_var_value: str


@dataclass(frozen=True)
class PartitionTrackingTestCase:
    description: str
    setup_sql: tuple[str, ...]
    expected_target_row_count: int
    expected_tracking_row_count: int
    expected_partition_values: tuple[str, ...]
    expected_statement_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExistingRelationTestCase:
    description: str
    expected_row_count: int
    expected_existing_was_none: bool
    setup_sql: tuple[str, ...] = field(default_factory=tuple)
    existing_database: str | None = None
    existing_schema: str | None = None
    existing_name: str | None = None
    existing_type: str | None = None


@dataclass(frozen=True)
class PrePromotionAuditTestCase:
    description: str
    expected_status: ExecutionStatus
    expected_failed_phase: ExecutionPhase
    expected_min_audit_row_count: int


@dataclass(frozen=True)
class PlaceholderExecutionTestCase:
    description: str
    model_sql: str
    placeholders: dict[str, str]
    substitutions: dict[str, str]
    expected_row_count: int


@dataclass(frozen=True)
class SchedulerRoutingTestCase:
    description: str
    project_files: dict[str, str]
    expected_status: BuildStatus
    expected_success_count: int
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...] = field(
        default_factory=tuple
    )
