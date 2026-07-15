"""Public selection-aware staleness classification entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.planner._helpers.pruning.selection_classifier import (
    classify_selection_staleness_warnings as _classify_selection_staleness_warnings,
)
from sqlbuild.compiler.planner.models import SelectionStalenessGraph, SelectionStalenessWarning


def classify_selection_staleness_warnings(
    graph: SelectionStalenessGraph,
) -> tuple[SelectionStalenessWarning, ...]:
    """Return stale warnings for selected models with changed upstreams outside the run set."""

    return _classify_selection_staleness_warnings(graph)
