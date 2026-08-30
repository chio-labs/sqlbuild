from dataclasses import dataclass

from sqlbuild.compiler.pipeline.models import PythonPlanEntry
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.python_nodes.models import SqlResourceRef


@dataclass(frozen=True)
class PythonRelationTargetsTestCase:
    description: str
    expected_source_relation: str


@dataclass(frozen=True)
class PythonRelationTargetScopeTestCase:
    description: str
    required_refs: frozenset[SqlResourceRef]
    expected_targets: dict[SqlResourceRef, str]


@dataclass(frozen=True)
class SelectedPythonRelationRefsTestCase:
    description: str
    selected_python_names: frozenset[str]
    expected_refs: frozenset[SqlResourceRef]


@dataclass(frozen=True)
class PlanWorkTestCase:
    description: str
    plan_output: PlanOutput
    python_plan_entries: tuple[PythonPlanEntry, ...]
    expected_has_work: bool


@dataclass(frozen=True)
class PipelinePhaseTimingTestCase:
    description: str
    clock_values: tuple[float, ...]
    expected_compile_seconds: float
    expected_planning_seconds: float
    expected_total_seconds: float
