from dataclasses import dataclass, field

from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build.models import BuildExecutionResult


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


@dataclass(frozen=True)
class BuildProgressFailureOutputTestCase:
    description: str
    node_result: object
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BuildProgressActiveSpinnerTestCase:
    description: str
    node_name: str
    node_type: str
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BuildProgressSpinnerLifecycleTestCase:
    description: str
    node_name: str
    node_type: str
    sleep_seconds: float
    completion_duration_ms: int
    expected_fragments: tuple[str, ...]
    expected_spinner_frames: tuple[str, ...]


@dataclass(frozen=True)
class ConnectionProgressTestCase:
    description: str
    connection_count: int
    elapsed_seconds: float
    expected_start: str
    expected_complete: str
    expected_error: str
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
