"""Public entrypoints for neutral graph changes-only propagation."""

from __future__ import annotations

from sqlbuild.compiler.planner.helpers.pruning.graph_changes_only import (
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

    return _build_graph_changes_only_propagation(
        upstream_deps=request.upstream_deps,
        model_keys=request.model_keys,
        selected_model_keys=request.selected_model_keys,
        current_model_keys=request.current_model_keys,
        run_model_keys=request.run_model_keys,
        run_parent_keys=request.run_parent_keys,
        selected_parent_keys=request.selected_parent_keys,
        identity_stale_model_keys=request.identity_stale_model_keys,
        version_mismatch_model_keys=request.version_mismatch_model_keys,
        changed_seed_keys=request.changed_seed_keys,
        changed_source_keys=request.changed_source_keys,
        blocked_source_keys=request.blocked_source_keys,
    )
