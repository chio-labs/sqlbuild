from dataclasses import dataclass, field

from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.types import ExecutionStatus
from sqlbuild.shared.types import ExecutionResourceKind
from tests.unit.src.sqlbuild.executor.build.helpers.helpers import ModelPlanOverride


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
    expected_load_status: ExecutionStatus
    expected_model_status: ExecutionStatus
    expected_execution_order: tuple[str, ...] = ()
    expected_model_rows: tuple[tuple[object, ...], ...] = ()


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
class BuildSchedulerNodeSourceWatermarkTestCase:
    description: str
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class BuildSchedulerNodeSourceWatermarkPayloadTestCase:
    description: str
    expected_source_hashes_by_node: dict[str, tuple[str, ...]]
    expected_source_kinds_by_node: dict[str, tuple[str, ...]]
    expected_unknown_reasons_by_node: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class BuildSchedulerMergedUpstreamWatermarkTestCase:
    description: str
    b_data_hash: str
    b_data_version: str
    c_data_hash: str
    c_data_version: str
    expected_source_hashes_by_node: dict[str, tuple[str, ...]]
    expected_source_kinds_by_node: dict[str, tuple[str, ...]]


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
