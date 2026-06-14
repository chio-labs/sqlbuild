from dataclasses import dataclass

from sqlbuild.compiler.pipeline.models import PythonPlanEntry
from sqlbuild.compiler.planner.models import PlanOutput


@dataclass(frozen=True)
class PythonRelationTargetsTestCase:
    description: str
    expected_source_relation: str


@dataclass(frozen=True)
class PlanWorkTestCase:
    description: str
    plan_output: PlanOutput
    python_plan_entries: tuple[PythonPlanEntry, ...]
    expected_has_work: bool
