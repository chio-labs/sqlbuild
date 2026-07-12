"""Public JSON plan formatting entrypoint."""

from __future__ import annotations

from sqlbuild.cli.output.helpers.plan_json import format_plan_json as _format_plan_json
from sqlbuild.compiler.pipeline.models import PythonPlanEntry
from sqlbuild.compiler.planner.models import PlanOutput


def format_plan_json(
    *, plan: PlanOutput, python_plan_entries: tuple[PythonPlanEntry, ...] = ()
) -> str:
    """Serialize a PlanOutput to JSON."""

    return _format_plan_json(plan=plan, python_plan_entries=python_plan_entries)
