"""Public entrypoint for planned work detection."""

from __future__ import annotations

from sqlbuild.compiler.pipeline.models import PythonPlanEntry
from sqlbuild.compiler.planner.models import PlanOutput


def plan_has_executable_work(
    plan: PlanOutput, *, python_plan_entries: tuple[PythonPlanEntry, ...] = ()
) -> bool:
    """Return whether a planned build has runtime work to execute."""

    return bool(
        plan.model_entries
        or plan.dependency_baseline_entries
        or plan.seed_entries
        or plan.source_load_entries
        or plan.function_entries
        or plan.audit_entries
        or plan.test_entries
        or python_plan_entries
    )
