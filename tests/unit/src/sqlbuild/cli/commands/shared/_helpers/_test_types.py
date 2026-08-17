from dataclasses import dataclass, field

from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.runtime.contracts.types import ExecutionResourceKind


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
    expected_reused: tuple[bool, ...] = field(default_factory=tuple)


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
    terminal_width: int = 120


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
    timeout_seconds: float
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
    status_text: str = "PASS"
    child_status_text: str = "PASS"
    error_code: str | None = None
    error_message: str | None = None


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
class BuildProgressLoadSkipOutputTestCase:
    description: str
    node_result: LoadExecutionResult
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...] = field(default_factory=tuple)
    use_color: bool = False


@dataclass(frozen=True)
class ConnectionProgressTestCase:
    description: str
    adapter_name: str
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
class PlanningCompletionMessageTestCase:
    description: str
    message: str
    expected_is_completion: bool


@dataclass(frozen=True)
class PlanningFinishTestCase:
    description: str
    messages_before_finish: tuple[str, ...]
    blank_line_after: bool
    messages_after_finish: tuple[str, ...]
    expected_output: str
