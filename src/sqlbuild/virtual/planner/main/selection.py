"""Public virtual selection entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.virtual.planner.helpers.planning import resolve_virtual_model_selection


def resolve_virtual_plan_model_selection(
    *,
    graph: ProjectGraph,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    default_selection: tuple[str, ...],
    stale_model_names: tuple[str, ...],
    include_stale_upstreams: bool = False,
    changes_only: bool = False,
) -> tuple[str, ...]:
    """Resolve the coherent virtual model selection for plan/build."""

    return resolve_virtual_model_selection(
        graph=graph,
        select=select,
        exclude=exclude,
        default_selection=default_selection,
        stale_model_names=stale_model_names,
        include_stale_upstreams=include_stale_upstreams,
        changes_only=changes_only,
    )
