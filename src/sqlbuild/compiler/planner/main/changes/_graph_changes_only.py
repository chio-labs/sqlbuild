"""Public entrypoints for neutral graph changes-only propagation."""

from __future__ import annotations

from sqlbuild.compiler.planner._helpers.pruning.graph_changes_only import (
    build_graph_changes_only_propagation as _build_graph_changes_only_propagation,
)
from sqlbuild.compiler.planner.models import (
    GraphChangesOnlyPropagationInput,
    GraphChangesOnlyPropagationResult,
)


def build_graph_changes_only_propagation(
    *, request: GraphChangesOnlyPropagationInput
) -> GraphChangesOnlyPropagationResult:
    """Propagate changes-only run/block decisions through a neutral model graph."""

    return _build_graph_changes_only_propagation(request=request)
