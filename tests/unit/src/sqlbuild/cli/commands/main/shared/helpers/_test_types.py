from dataclasses import dataclass, field

from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.auditing.models import AuditExecutionResult


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
class ResolveProjectConnectionConfigTestCase:
    description: str
    project_dir_name: str
    expected_connection: dict[str, object]
