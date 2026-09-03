from collections.abc import Callable
from dataclasses import dataclass, field

from sqlbuild.adapter.contract.models import RelationInfo
from sqlbuild.adapter.contract.types import RetentionChangePhase
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.compiler.planner.types import RetentionPlanPhase
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.runtime.contracts.types import ExecutionResourceKind
from tests.unit.src.sqlbuild.executor.build._helpers.helpers import ModelPlanOverride


@dataclass(frozen=True)
class AuditExecutionIndexTestCase:
    description: str
    expected_model_audit_count: int
    expected_end_audit_count: int


@dataclass(frozen=True)
class LifecycleProgressTestCase:
    description: str
    expected_event_types: tuple[str, ...]


@dataclass(frozen=True)
class BuildOutputTestCase:
    """Test case for build output formatting."""

    description: str
    result: BuildExecutionResult
    expected_output_fragments: tuple[str, ...]
    expected_absent_fragments: tuple[str, ...] = field(default_factory=tuple)
    model_plan_overrides: tuple[ModelPlanOverride, ...] = field(default_factory=tuple)
    target: str | None = None
    concurrency: int = 1
    elapsed_seconds: float = 1.5
    verbose: bool = False
    use_color: bool = False


@dataclass(frozen=True)
class BuildSchedulerSourceLoadTestCase:
    description: str
    source_status: ExecutionStatus
    loader_factory: Callable[..., DiscoveredLoaderFunction]
    expected_load_status: ExecutionStatus
    expected_model_status: ExecutionStatus
    source_meta: dict[str, object]
    expected_resource_kind: ExecutionResourceKind
    expected_execution_order: tuple[str, ...] = ()
    expected_model_rows: tuple[tuple[object, ...], ...] = ()


@dataclass(frozen=True)
class BuildRetentionPhaseTestCase:
    description: str
    phase: RetentionPlanPhase
    expected_statements: tuple[str, ...]


@dataclass(frozen=True)
class BuildModelRetentionReconciliationTestCase:
    description: str
    desired_days: int
    effective_days: int
    change_phase: RetentionChangePhase
    expected_statements: tuple[str, ...]


@dataclass(frozen=True)
class TableTypeConversionTestCase:
    description: str
    relation_snapshots: tuple[tuple[RelationInfo, ...], ...]
    expected_statements: tuple[str, ...]
    desired_type: str = "permanent"
    actual_type: str = "transient"


@dataclass(frozen=True)
class TableTypeConversionErrorTestCase:
    description: str
    relation_snapshots: tuple[tuple[RelationInfo, ...], ...]
    expected_error_fragment: str
    expected_statements: tuple[str, ...]


@dataclass(frozen=True)
class BuildSchedulerModelHookTestCase:
    description: str
    hook_raises: bool
    expected_model_status: ExecutionStatus
    expected_events: tuple[str, ...]
    expected_model_rows: tuple[tuple[object, ...], ...] = ()


@dataclass(frozen=True)
class BuildSchedulerPreHookSkipTestCase:
    description: str
    expected_model_statuses: tuple[ExecutionStatus, ...]
    expected_execution_order: tuple[str, ...]


@dataclass(frozen=True)
class BuildSchedulerPlannedSkipTestCase:
    description: str
    expected_model_statuses: tuple[ExecutionStatus, ...]
    expected_build_status: BuildStatus
    expected_failure_count: int
    expected_skip_reason: str
    expected_execution_order: tuple[str, ...]


@dataclass(frozen=True)
class BuildSourceNodeExecutionTestCase:
    description: str
    source_name: str
    loader_name: str
    expected_progress_event: str
    expected_start_event: tuple[str, ExecutionResourceKind]
    expected_status: ExecutionStatus
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class ExternalBuildSourceLoadTestCase:
    """One pre-connection build source-load behavior case."""

    description: str
    source_name: str
    loader_name: str
    expected_status: ExecutionStatus
    expected_completed_key_count: int
    expected_lifecycle_message: str


@dataclass(frozen=True)
class AbbreviatedRowCountTestCase:
    description: str
    count: int
    expected_output: str


@dataclass(frozen=True)
class BatchSummaryTestCase:
    description: str
    batch_count: int | None
    rows_affected: int | None
    cursor_range_start: str | None
    cursor_range_end: str | None
    cursor_type: str | None
    cursor_grain: str | None
    expected_fragments: tuple[str, ...]
    batch_size: str | None = None
    expected_absent_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_none: bool = False
