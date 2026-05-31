"""Planner scope resolution helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import (
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledSeed,
    CompiledSource,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.helpers.auto_load import managed_source_upstream_keys
from sqlbuild.compiler.planner.helpers.graph import (
    build_downstream_deps,
    build_upstream_deps,
    topologically_order_keys,
)
from sqlbuild.compiler.planner.helpers.loader_dag import expand_selected_loader_dependencies
from sqlbuild.compiler.planner.helpers.plan_entry import build_path_index, build_tag_index
from sqlbuild.compiler.planner.helpers.selectors import resolve_selectors
from sqlbuild.compiler.planner.models import PlannerScope


def build_planner_scope(
    *,
    project: CompiledProject,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    auto_load_sources: bool,
    selected_keys: frozenset[CompiledObjectKey] | None = None,
) -> PlannerScope:
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = build_upstream_deps(
        project
    )
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = build_downstream_deps(
        upstream_deps
    )
    all_keys: dict[str, CompiledObjectKey] = _build_all_keys(project)
    tag_index: dict[str, frozenset[CompiledObjectKey]] = build_tag_index(project)
    path_idx: dict[CompiledObjectKey, str] = build_path_index(project)
    resolved_selected_keys: frozenset[CompiledObjectKey] = (
        selected_keys
        if selected_keys is not None
        else resolve_selectors(
            select=select,
            exclude=exclude,
            all_keys=all_keys,
            upstream=upstream_deps,
            downstream=downstream_deps,
            tag_index=tag_index,
            path_index=path_idx,
        )
    )
    if auto_load_sources:
        resolved_selected_keys = resolved_selected_keys | managed_source_upstream_keys(
            selected_keys=resolved_selected_keys,
            upstream_deps=upstream_deps,
            project=project,
        )
    if auto_load_sources or any(
        key.resource_type == CompiledResourceType.SOURCE for key in resolved_selected_keys
    ):
        resolved_selected_keys, upstream_deps = expand_selected_loader_dependencies(
            project=project,
            selected_keys=resolved_selected_keys,
            upstream_deps=upstream_deps,
        )
        downstream_deps = build_downstream_deps(upstream_deps)
    return PlannerScope(
        upstream_deps=upstream_deps,
        downstream_deps=downstream_deps,
        all_keys=all_keys,
        models_by_name={model.name: model for model in project.models},
        selected_keys=resolved_selected_keys,
        execution_order=topologically_order_keys(upstream_deps),
    )


def _build_all_keys(project: CompiledProject) -> dict[str, CompiledObjectKey]:
    keys: dict[str, CompiledObjectKey] = {}
    model: CompiledModel
    for model in project.models:
        keys[model.name] = model.key
    source: CompiledSource
    for source in project.sources:
        keys[source.name] = source.key
    seed: CompiledSeed
    for seed in project.seeds:
        keys[seed.name] = seed.key
    function: CompiledFunction
    for function in project.functions:
        keys[function.name] = function.key
    return keys
