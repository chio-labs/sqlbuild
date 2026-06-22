"""Pure selection-aware staleness classification helpers."""

from __future__ import annotations

from sqlbuild.compiler.planner.models import (
    SelectionStalenessGraph,
    SelectionStalenessNodeKey,
    SelectionStalenessWarning,
)


def classify_selection_staleness_warnings(
    graph: SelectionStalenessGraph,
) -> tuple[SelectionStalenessWarning, ...]:
    """Return stale warnings for selected models with changed upstreams outside the run set."""

    warnings: list[SelectionStalenessWarning] = []
    for model_name in sorted(graph.selected_model_names):
        triggers: tuple[str, ...] = _changed_upstream_names(
            graph=graph,
            model_key=SelectionStalenessNodeKey(
                resource_type="model",
                name=model_name,
            ),
        )
        if triggers:
            warnings.append(
                SelectionStalenessWarning(model_name=model_name, trigger_names=triggers)
            )
    return tuple(warnings)


def _changed_upstream_names(
    *,
    graph: SelectionStalenessGraph,
    model_key: SelectionStalenessNodeKey,
) -> tuple[str, ...]:
    names: set[str] = set()
    visiting: set[SelectionStalenessNodeKey] = set()
    stale_by_key: dict[SelectionStalenessNodeKey, bool] = {}

    def visit(upstream_key: SelectionStalenessNodeKey) -> bool:
        cached: bool | None = stale_by_key.get(upstream_key)
        if cached is not None:
            return cached
        if upstream_key in visiting:
            return False
        visiting.add(upstream_key)
        is_stale: bool
        if upstream_key.resource_type == "model":
            in_run_set: bool = upstream_key.name in graph.run_model_names
            own_changed: bool = upstream_key.name in graph.changed_model_names
            if own_changed and not in_run_set:
                is_stale = True
                names.add(upstream_key.name)
            else:
                ancestor_stale: bool = False
                parent_key: SelectionStalenessNodeKey
                for parent_key in graph.upstream_deps.get(upstream_key, ()):
                    ancestor_stale = visit(parent_key) or ancestor_stale
                    if _run_parent_changed(graph=graph, parent_key=parent_key):
                        ancestor_stale = True
                is_stale = ancestor_stale
                if ancestor_stale and not in_run_set and upstream_key != model_key:
                    names.add(upstream_key.name)
        elif upstream_key.resource_type == "seed":
            changed: bool = upstream_key.name in graph.changed_seed_names
            if changed and upstream_key.name not in graph.run_seed_names:
                names.add(upstream_key.name)
            is_stale = changed
        elif upstream_key.resource_type == "source":
            changed = upstream_key.name in graph.changed_source_names
            if changed and upstream_key.name not in graph.run_source_names:
                names.add(upstream_key.name)
            is_stale = changed
        else:
            is_stale = False
        visiting.remove(upstream_key)
        stale_by_key[upstream_key] = is_stale
        return is_stale

    upstream_key: SelectionStalenessNodeKey
    for upstream_key in graph.upstream_deps.get(model_key, ()):
        visit(upstream_key)
    return tuple(sorted(names))


def _run_parent_changed(
    *, graph: SelectionStalenessGraph, parent_key: SelectionStalenessNodeKey
) -> bool:
    if parent_key.resource_type == "model":
        return (
            parent_key.name in graph.run_model_names
            and parent_key.name in graph.changed_model_names
        )
    if parent_key.resource_type == "seed":
        return (
            parent_key.name in graph.run_seed_names and parent_key.name in graph.changed_seed_names
        )
    if parent_key.resource_type == "source":
        return (
            parent_key.name in graph.run_source_names
            and parent_key.name in graph.changed_source_names
        )
    return False
