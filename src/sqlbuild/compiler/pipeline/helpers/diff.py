"""Diff pipeline assembly helpers."""

from __future__ import annotations

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import (
    CompiledObjectKey,
    CompiledProject,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compiled_project import build_compiled_project
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.shared.types import ExternalReferenceResolver


def compile_project_for_diff_environment(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    environment_name: str,
    no_sql_validation: bool,
    external_reference_resolver: ExternalReferenceResolver | None = None,
) -> CompiledProject:
    """Compile a project for one diff environment."""

    return build_compiled_project(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        selected_environment=environment_name,
        no_sql_validation=no_sql_validation,
        external_reference_resolver=external_reference_resolver,
    )


def resolve_diff_model_names(
    *,
    project: CompiledProject,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
) -> tuple[str, ...]:
    """Resolve diff selectors to model names only."""

    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = _build_upstream_deps(
        project
    )
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = (
        _build_downstream_deps(upstream_deps)
    )
    all_keys: dict[str, CompiledObjectKey] = {
        **{model.name: model.key for model in project.models},
        **{source.name: source.key for source in project.sources},
        **{seed.name: seed.key for seed in project.seeds},
    }
    selected_keys: frozenset[CompiledObjectKey] = _resolve_model_selectors(
        select=select,
        exclude=exclude,
        all_keys=all_keys,
        upstream=upstream_deps,
        downstream=downstream_deps,
        tag_index=_build_tag_index(project),
        path_index=_build_path_index(project),
    )
    return tuple(
        model.name
        for model in project.models
        if model.key in selected_keys and model.key.resource_type == CompiledResourceType.MODEL
    )


def _build_upstream_deps(
    project: CompiledProject,
) -> dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]:
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = {}
    upstream.update({model.key: model.deps for model in project.models})
    upstream.update({source.key: source.deps for source in project.sources})
    upstream.update({seed.key: seed.deps for seed in project.seeds})
    return upstream


def _build_downstream_deps(
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]:
    downstream: dict[CompiledObjectKey, list[CompiledObjectKey]] = {}
    key: CompiledObjectKey
    for key in upstream:
        downstream.setdefault(key, [])
    for key, dep_keys in upstream.items():
        dep_key: CompiledObjectKey
        for dep_key in dep_keys:
            downstream.setdefault(dep_key, []).append(key)
    return {
        key: tuple(sorted(values, key=lambda item: (item.resource_type, item.name)))
        for key, values in downstream.items()
    }


def _build_tag_index(project: CompiledProject) -> dict[str, frozenset[CompiledObjectKey]]:
    index: dict[str, set[CompiledObjectKey]] = {}
    for model in project.models:
        raw_tags: object | None = model.config.values.get("tags")
        if not isinstance(raw_tags, list | tuple):
            continue
        tag: object
        for tag in raw_tags:
            if isinstance(tag, str):
                index.setdefault(tag, set()).add(model.key)
    return {tag: frozenset(keys) for tag, keys in index.items()}


def _build_path_index(project: CompiledProject) -> dict[CompiledObjectKey, str]:
    return {
        model.key: str(model.relative_path.parent).removeprefix("models/")
        for model in project.models
    }


def _resolve_model_selectors(
    *,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    all_keys: dict[str, CompiledObjectKey],
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    tag_index: dict[str, frozenset[CompiledObjectKey]],
    path_index: dict[CompiledObjectKey, str],
) -> frozenset[CompiledObjectKey]:
    selected: set[CompiledObjectKey] = set()
    raw_select: str
    for raw_select in select:
        token: str
        for token in raw_select.split():
            selected.update(
                _resolve_selector_token(
                    token=token,
                    all_keys=all_keys,
                    upstream=upstream,
                    downstream=downstream,
                    tag_index=tag_index,
                    path_index=path_index,
                )
            )
    excluded: set[CompiledObjectKey] = set()
    raw_exclude: str
    for raw_exclude in exclude:
        for token in raw_exclude.split():
            excluded.update(
                _resolve_selector_token(
                    token=token,
                    all_keys=all_keys,
                    upstream=upstream,
                    downstream=downstream,
                    tag_index=tag_index,
                    path_index=path_index,
                )
            )
    return frozenset(selected - excluded)


def _resolve_selector_token(
    *,
    token: str,
    all_keys: dict[str, CompiledObjectKey],
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    tag_index: dict[str, frozenset[CompiledObjectKey]],
    path_index: dict[CompiledObjectKey, str],
) -> frozenset[CompiledObjectKey]:
    parts: list[str] = token.split(",")
    if len(parts) > 1:
        resolved_parts: list[frozenset[CompiledObjectKey]] = [
            _resolve_selector_token(
                token=part,
                all_keys=all_keys,
                upstream=upstream,
                downstream=downstream,
                tag_index=tag_index,
                path_index=path_index,
            )
            for part in parts
        ]
        result: frozenset[CompiledObjectKey] = resolved_parts[0]
        part_result: frozenset[CompiledObjectKey]
        for part_result in resolved_parts[1:]:
            result = result & part_result
        return result

    upstream_requested: bool = token.startswith("+")
    downstream_requested: bool = token.endswith("+")
    core: str = token.lstrip("+").rstrip("+")
    if not core:
        raise PlannerInputError("empty selector", code="S001")
    if core.startswith("tag:"):
        keys: frozenset[CompiledObjectKey] = tag_index.get(core.removeprefix("tag:"), frozenset())
        if not keys:
            raise PlannerInputError(
                f"no models found with tag '{core.removeprefix('tag:')}'",
                code="S008",
            )
        return _expand_keys(keys, upstream_requested, downstream_requested, upstream, downstream)
    if core.startswith("path:") or "/" in core:
        path_value: str = core.removeprefix("path:").strip("/")
        keys = frozenset(
            key
            for key, folder in path_index.items()
            if folder == path_value or folder.startswith(f"{path_value}/")
        )
        if not keys:
            raise PlannerInputError(f"no models found under path '{path_value}'", code="S009")
        return _expand_keys(keys, upstream_requested, downstream_requested, upstream, downstream)

    key: CompiledObjectKey | None = all_keys.get(core)
    if key is None:
        raise PlannerInputError(f"unknown selector name '{core}'", code="S007")
    return _expand_keys(
        frozenset((key,)), upstream_requested, downstream_requested, upstream, downstream
    )


def _expand_keys(
    keys: frozenset[CompiledObjectKey],
    upstream_requested: bool,
    downstream_requested: bool,
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> frozenset[CompiledObjectKey]:
    expanded: set[CompiledObjectKey] = set(keys)
    key: CompiledObjectKey
    for key in keys:
        if upstream_requested:
            expanded.update(_expand_graph(key, upstream))
        if downstream_requested:
            expanded.update(_expand_graph(key, downstream))
    return frozenset(expanded)


def _expand_graph(
    key: CompiledObjectKey,
    graph: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> frozenset[CompiledObjectKey]:
    visited: set[CompiledObjectKey] = set()
    stack: list[CompiledObjectKey] = [key]
    while stack:
        current: CompiledObjectKey = stack.pop()
        neighbor: CompiledObjectKey
        for neighbor in graph.get(current, ()):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            stack.append(neighbor)
    return frozenset(visited)
