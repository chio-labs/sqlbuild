"""Public planner scope entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.planner._helpers.graph.scope import build_planner_scope as _build
from sqlbuild.compiler.planner.models import PlannerScope


def build_planner_scope(
    *,
    project: CompiledProject,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    auto_load_sources: bool = False,
    selected_keys: frozenset[CompiledObjectKey] | None = None,
) -> PlannerScope:
    """Build the resolved planner graph scope for a project."""

    return _build(
        project=project,
        select=select,
        exclude=exclude,
        auto_load_sources=auto_load_sources,
        selected_keys=selected_keys,
    )
