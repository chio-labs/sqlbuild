"""Runtime SQL relation maps for Python node contexts."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.pipeline._helpers.relation_targets import (
    build_python_relation_targets_impl,
)
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.python_nodes.models import SqlResourceRef


def build_python_relation_targets(
    *,
    adapter: BaseAdapter,
    project: CompiledProject,
    plan_output: PlanOutput,
    required_refs: frozenset[SqlResourceRef] | None = None,
) -> dict[SqlResourceRef, str]:
    """Return adapter-qualified runtime relations required by selected Python nodes."""

    return build_python_relation_targets_impl(
        adapter=adapter, project=project, plan_output=plan_output, required_refs=required_refs
    )
