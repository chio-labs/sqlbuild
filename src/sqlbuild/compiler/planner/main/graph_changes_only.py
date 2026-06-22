"""Public entrypoints for neutral graph changes-only propagation."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.compiler.planner.helpers.graph_changes_only import (
    build_graph_changes_only_propagation as _build_graph_changes_only_propagation,
)
from sqlbuild.compiler.planner.models import GraphChangesOnlyPropagationResult, GraphNodeKey


def build_graph_changes_only_propagation(
    *,
    upstream_deps: Mapping[GraphNodeKey, tuple[GraphNodeKey, ...]],
    model_keys: frozenset[GraphNodeKey],
    selected_model_keys: frozenset[GraphNodeKey],
    current_model_keys: frozenset[GraphNodeKey],
    run_model_keys: frozenset[GraphNodeKey],
    version_mismatch_model_keys: frozenset[GraphNodeKey],
    run_parent_keys: frozenset[GraphNodeKey] | None = None,
    selected_parent_keys: frozenset[GraphNodeKey] | None = None,
    identity_stale_model_keys: frozenset[GraphNodeKey] = frozenset(),
    changed_seed_keys: frozenset[GraphNodeKey] = frozenset(),
    changed_source_keys: frozenset[GraphNodeKey] = frozenset(),
    blocked_source_keys: frozenset[GraphNodeKey] = frozenset(),
) -> GraphChangesOnlyPropagationResult:
    """Propagate changes-only run/block decisions through a neutral model graph."""

    return _build_graph_changes_only_propagation(
        upstream_deps=upstream_deps,
        model_keys=model_keys,
        selected_model_keys=selected_model_keys,
        current_model_keys=current_model_keys,
        run_model_keys=run_model_keys,
        run_parent_keys=run_parent_keys,
        selected_parent_keys=selected_parent_keys,
        identity_stale_model_keys=identity_stale_model_keys,
        version_mismatch_model_keys=version_mismatch_model_keys,
        changed_seed_keys=changed_seed_keys,
        changed_source_keys=changed_source_keys,
        blocked_source_keys=blocked_source_keys,
    )
