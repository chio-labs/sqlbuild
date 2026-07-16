"""Pure selection-aware staleness classification helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import (
    SelectionStalenessGraph,
    SelectionStalenessNodeKey,
    SelectionStalenessWarning,
)

_STALE_TRIGGER_DISPLAY_LIMIT: int = 5


def format_stale_upstream_warning_message(
    *,
    model_label: str,
    model_name: str,
    trigger_label: str,
    trigger_names: tuple[str, ...],
) -> str:
    """Build a multi-line stale-selection warning: summary, capped bullet list, single hint."""

    count: int = len(trigger_names)
    displayed: tuple[str, ...] = trigger_names[:_STALE_TRIGGER_DISPLAY_LIMIT]
    lines: list[str] = [
        f"{model_label} '{model_name}' will build on {count} stale {trigger_label} "
        "not selected for rebuild:"
    ]
    name: str
    for name in displayed:
        lines.append(f"    - {name}")
    if count > _STALE_TRIGGER_DISPLAY_LIMIT:
        lines.append(f"    +{count - _STALE_TRIGGER_DISPLAY_LIMIT} more")
    lines.append(f"    rebuild the closure to refresh them: --select +{model_name}")
    return "\n".join(lines)


def classify_selection_staleness_warnings(
    graph: SelectionStalenessGraph,
) -> tuple[SelectionStalenessWarning, ...]:
    """Return stale warnings for selected models with changed upstreams outside the run set."""

    warnings: list[SelectionStalenessWarning] = []
    for model_name in sorted(graph.selected_model_names):
        triggers: tuple[str, ...] = _changed_upstream_names(
            graph=graph,
            model_key=SelectionStalenessNodeKey(
                resource_type=CompiledResourceType.MODEL.value,
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

    def visit(
        *,
        upstream_key: SelectionStalenessNodeKey,
        found_names: set[str],
        visiting_keys: set[SelectionStalenessNodeKey],
        stale_cache: dict[SelectionStalenessNodeKey, bool],
    ) -> tuple[
        bool, set[str], set[SelectionStalenessNodeKey], dict[SelectionStalenessNodeKey, bool]
    ]:
        cached: bool | None = stale_cache.get(upstream_key)
        if cached is not None:
            return cached, found_names, visiting_keys, stale_cache
        if upstream_key in visiting_keys:
            return False, found_names, visiting_keys, stale_cache
        visiting_keys = visiting_keys | {upstream_key}
        is_stale: bool
        if upstream_key.resource_type == CompiledResourceType.MODEL.value:
            in_run_set: bool = upstream_key.name in graph.run_model_names
            own_changed: bool = upstream_key.name in graph.changed_model_names
            if own_changed and not in_run_set:
                is_stale = True
                found_names = found_names | {upstream_key.name}
            else:
                ancestor_stale: bool = False
                parent_key: SelectionStalenessNodeKey
                for parent_key in graph.upstream_deps.get(upstream_key, ()):
                    parent_stale, found_names, visiting_keys, stale_cache = visit(
                        upstream_key=parent_key,
                        found_names=found_names,
                        visiting_keys=visiting_keys,
                        stale_cache=stale_cache,
                    )
                    ancestor_stale = parent_stale or ancestor_stale
                    if _run_parent_changed(graph=graph, parent_key=parent_key):
                        ancestor_stale = True
                is_stale = ancestor_stale
                if ancestor_stale and not in_run_set and upstream_key != model_key:
                    found_names = found_names | {upstream_key.name}
        elif upstream_key.resource_type == CompiledResourceType.SEED.value:
            changed: bool = upstream_key.name in graph.changed_seed_names
            if changed and upstream_key.name not in graph.run_seed_names:
                found_names = found_names | {upstream_key.name}
            is_stale = changed
        elif upstream_key.resource_type == CompiledResourceType.SOURCE.value:
            changed = upstream_key.name in graph.changed_source_names
            if changed and upstream_key.name not in graph.run_source_names:
                found_names = found_names | {upstream_key.name}
            is_stale = changed
        else:
            is_stale = False
        visiting_keys = visiting_keys - {upstream_key}
        return is_stale, found_names, visiting_keys, {**stale_cache, upstream_key: is_stale}

    upstream_key: SelectionStalenessNodeKey
    for upstream_key in graph.upstream_deps.get(model_key, ()):
        _, names, visiting, stale_by_key = visit(
            upstream_key=upstream_key,
            found_names=names,
            visiting_keys=visiting,
            stale_cache=stale_by_key,
        )
    return tuple(sorted(names))


def _run_parent_changed(
    *, graph: SelectionStalenessGraph, parent_key: SelectionStalenessNodeKey
) -> bool:
    if parent_key.resource_type == CompiledResourceType.MODEL.value:
        return (
            parent_key.name in graph.run_model_names
            and parent_key.name in graph.changed_model_names
        )
    if parent_key.resource_type == CompiledResourceType.SEED.value:
        return (
            parent_key.name in graph.run_seed_names and parent_key.name in graph.changed_seed_names
        )
    if parent_key.resource_type == CompiledResourceType.SOURCE.value:
        return (
            parent_key.name in graph.run_source_names
            and parent_key.name in graph.changed_source_names
        )
    return False
