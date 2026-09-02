from dataclasses import dataclass, field

from sqlbuild.compiler.pipeline.models import PythonPlanEntry
from sqlbuild.compiler.planner.models import PlanOutput


@dataclass(frozen=True)
class JsonOutputTestCase:
    description: str
    plan_output: PlanOutput
    expected_keys: tuple[str, ...]
    python_plan_entries: tuple[PythonPlanEntry, ...] = field(default_factory=tuple)
    expected_fragments: tuple[str, ...] = field(default_factory=tuple)
    unexpected_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FutureCursorPlanJsonTestCase:
    description: str
    expected_action: str


@dataclass(frozen=True)
class SelectionDiagnosticsPlanJsonTestCase:
    description: str
    enabled: bool
    expected_mode: str


@dataclass(frozen=True)
class MicrobatchLimitPlanJsonTestCase:
    description: str
    expected_limit: int
    expected_count: int
    expected_action: str
    expected_warning: str
