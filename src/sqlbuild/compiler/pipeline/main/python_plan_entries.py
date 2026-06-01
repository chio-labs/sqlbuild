"""Public entrypoint for Python-node plan display entries."""

from __future__ import annotations

from sqlbuild.compiler.pipeline.helpers.python_plan_entries import (
    build_python_plan_entries as _build_python_plan_entries,
)
from sqlbuild.compiler.pipeline.models import PythonPlanEntry
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph, PythonSqlRunLifecyclePlan


def build_python_plan_entries(
    *, lifecycle_plan: PythonSqlRunLifecyclePlan, python_graph: PythonNodeGraph
) -> tuple[PythonPlanEntry, ...]:
    """Return display entries for a lifecycle-aware Python-node plan."""

    return _build_python_plan_entries(lifecycle_plan=lifecycle_plan, python_graph=python_graph)
