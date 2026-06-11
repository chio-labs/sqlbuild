"""Public virtual selection entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.types import WorkSelectionPolicy
from sqlbuild.virtual.planner.helpers.planning import resolve_virtual_model_selection


def resolve_virtual_plan_model_selection(
    *,
    graph: ProjectGraph,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    default_selection: tuple[str, ...],
    stale_model_names: tuple[str, ...],
    include_stale_upstreams: bool = False,
    work_selection_policy: WorkSelectionPolicy = WorkSelectionPolicy.ALL_SELECTED,
) -> tuple[str, ...]:
    """Resolve the coherent virtual model selection for plan/build."""

    return resolve_virtual_model_selection(
        graph=graph,
        select=select,
        exclude=exclude,
        default_selection=default_selection,
        stale_model_names=stale_model_names,
        include_stale_upstreams=include_stale_upstreams,
        work_selection_policy=work_selection_policy,
    )
