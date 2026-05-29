from dataclasses import dataclass, field

from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.shared.types import ExecutionResourceKind
from sqlbuild.spec.models.project import SnapshotsConfig


@dataclass(frozen=True)
class ModeGuardTestCase:
    description: str
    environment_mode: str
    command_name: str
    expected_error_fragment: str | None
    defer_to: str | None = None


@dataclass(frozen=True)
class JsonOutputTestCase:
    description: str
    plan_output: PlanOutput
    expected_keys: tuple[str, ...]
    expected_fragments: tuple[str, ...] = field(default_factory=tuple)
    unexpected_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TruncateNameTestCase:
    description: str
    name: str
    width: int
    expected_result: str


@dataclass(frozen=True)
class AuditAggregationTestCase:
    description: str
    audit_results: tuple[AuditExecutionResult, ...]
    expected_entry_count: int
    expected_labels: tuple[str, ...]
    expected_outcomes: tuple[AuditOutcome, ...]
    expected_batch_totals: tuple[int, ...]
    expected_batch_passes: tuple[int, ...]


@dataclass(frozen=True)
class BuildFooterTestCase:
    description: str
    result: BuildExecutionResult
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...] = field(default_factory=tuple)
    use_color: bool = False


@dataclass(frozen=True)
class ExecutionHeaderTestCase:
    description: str
    command: str
    target: str | None
    concurrency: int
    use_color: bool
    expected_output: str


@dataclass(frozen=True)
class BuildProgressFailureOutputTestCase:
    description: str
    node_result: object
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...] = field(default_factory=tuple)
    use_color: bool = False


@dataclass(frozen=True)
class BuildProgressModelOutputTestCase:
    description: str
    node_result: ModelExecutionResult
    plan_output: PlanOutput
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...] = field(default_factory=tuple)
    use_color: bool = False


@dataclass(frozen=True)
class BuildProgressActiveSpinnerTestCase:
    description: str
    node_name: str
    node_type: ExecutionResourceKind
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BuildProgressSpinnerLifecycleTestCase:
    description: str
    node_name: str
    node_type: ExecutionResourceKind
    sleep_seconds: float
    completion_duration_ms: int
    expected_fragments: tuple[str, ...]
    expected_spinner_frames: tuple[str, ...]


@dataclass(frozen=True)
class NestedProgressChildRowsTestCase:
    description: str
    item_name: str
    name_width: int
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BuildProgressSqlTestRowsTestCase:
    description: str
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BuildProgressLoadLogTestCase:
    description: str
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...] = field(default_factory=tuple)
    use_color: bool = False


@dataclass(frozen=True)
class ConnectionProgressTestCase:
    description: str
    connection_count: int
    elapsed_seconds: float
    expected_start: str
    expected_complete: str
    expected_error: str
    blank_line_before_start: bool = False
    blank_line_after_complete: bool = False
    use_color: bool = False
    expected_lines: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlanningProgressTestCase:
    description: str
    messages: tuple[str, ...]
    expected_output: str
    use_color: bool = False


@dataclass(frozen=True)
class ResolveProjectConnectionConfigTestCase:
    description: str
    project_dir_name: str
    expected_connection: dict[str, object]
    expected_warning_fragment: str = ""


@dataclass(frozen=True)
class ResolveEnvironmentConnectionConfigTestCase:
    description: str
    environment_name: str
    expected_connection: dict[str, object]


@dataclass(frozen=True)
class ResolveConnectionConfigWarningTestCase:
    description: str
    raw_config: dict[str, object]
    adapter_name: str
    expected_connection: dict[str, object]
    expected_warning: str


@dataclass(frozen=True)
class SnapshotFullRefreshPolicyTestCase:
    description: str
    plan_output: PlanOutput
    snapshots_config: SnapshotsConfig
    allow_snapshot_full_refresh: bool
    expected_error_fragment: str | None = None
    expected_help_fragment: str = ""
    expected_output: str = ""
    input_text: str = ""
    input_is_tty: bool = False
