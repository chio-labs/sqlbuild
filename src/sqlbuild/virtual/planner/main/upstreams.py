"""Public virtual upstream closure helpers."""

from __future__ import annotations

from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.virtual.planner.helpers.planning import build_stale_required_upstream_closure


def build_virtual_stale_required_upstream_closure(
    *,
    graph: ProjectGraph,
    selected_model_names: tuple[str, ...],
    stale_model_names: tuple[str, ...],
) -> tuple[str, ...]:
    """Return stale required upstreams for a selected virtual model scope."""

    return build_stale_required_upstream_closure(
        graph=graph,
        selected_model_names=selected_model_names,
        stale_model_names=stale_model_names,
    )
