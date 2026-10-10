"""Planner scope resolution helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.graph.main._native_project_graph import build_native_project_graph
from sqlbuild.compiler.graph.main.project_lineage_views import project_lineage_views
from sqlbuild.compiler.planner._helpers.graph.auto_load import managed_source_upstream_keys
from sqlbuild.compiler.planner._helpers.graph.core import (
    build_downstream_deps,
    build_execution_edge_origins,
    build_execution_upstream_deps,
    topologically_order_keys,
)
from sqlbuild.compiler.planner._helpers.graph.loader_dag import expand_selected_loader_dependencies
from sqlbuild.compiler.planner._helpers.graph.selectors import (
    parse_selector,
    resolve_graph_selectors,
)
from sqlbuild.compiler.planner.models import (
    ParsedSelector,
    PathSelector,
    PlannerScope,
    SqlTestSelection,
)
from sqlbuild.compiler.planner.types import SelectorKind


def build_planner_scope(
    *,
    project: CompiledProject,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    auto_load_sources: bool,
    selected_keys: frozenset[CompiledObjectKey] | None = None,
    python_read_source_names: frozenset[str] = frozenset(),
    sql_test_selection: SqlTestSelection | None = None,
) -> PlannerScope:
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = (
        build_execution_upstream_deps(project)
    )
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = build_downstream_deps(
        upstream_deps
    )
    all_keys: dict[str, CompiledObjectKey] = project_lineage_views(project).all_keys
    resolved_selected_keys: frozenset[CompiledObjectKey] = (
        selected_keys
        if selected_keys is not None
        else resolve_graph_selectors(
            graph=build_native_project_graph(project), select=select, exclude=exclude
        )
    )
    executable_dependency_source_keys: frozenset[CompiledObjectKey] = (
        _upstream_source_selector_keys(
            select=select,
            all_keys=all_keys,
            selected_keys=resolved_selected_keys,
        )
    )
    if auto_load_sources:
        auto_loaded_source_keys: frozenset[CompiledObjectKey] = managed_source_upstream_keys(
            selected_keys=resolved_selected_keys,
            upstream_deps=upstream_deps,
            project=project,
        )
        resolved_selected_keys = resolved_selected_keys | auto_loaded_source_keys
        executable_dependency_source_keys = (
            executable_dependency_source_keys | auto_loaded_source_keys
        )
    executable_dependency_source_keys = executable_dependency_source_keys & resolved_selected_keys
    if auto_load_sources or any(
        key.resource_type == CompiledResourceType.SOURCE for key in resolved_selected_keys
    ):
        resolved_selected_keys, upstream_deps = expand_selected_loader_dependencies(
            project=project,
            selected_keys=resolved_selected_keys,
            upstream_deps=upstream_deps,
            executable_dependency_source_keys=executable_dependency_source_keys,
        )
        downstream_deps = build_downstream_deps(upstream_deps)
    return PlannerScope(
        upstream_deps=upstream_deps,
        downstream_deps=downstream_deps,
        all_keys=all_keys,
        models_by_name={model.name: model for model in project.models},
        selected_keys=resolved_selected_keys,
        execution_order=topologically_order_keys(
            upstream=upstream_deps,
            injected_edge_origins=build_execution_edge_origins(project),
        ),
        user_selected_keys=resolved_selected_keys,
        python_read_source_names=python_read_source_names,
        sql_test_selection=sql_test_selection or SqlTestSelection(),
    )


def _upstream_source_selector_keys(
    *,
    select: tuple[str, ...],
    all_keys: dict[str, CompiledObjectKey],
    selected_keys: frozenset[CompiledObjectKey],
) -> frozenset[CompiledObjectKey]:
    keys: set[CompiledObjectKey] = set()
    raw_select: str
    for raw_select in select:
        token: str
        for token in raw_select.split():
            part: str
            for part in token.split(","):
                parsed: ParsedSelector | PathSelector = parse_selector(part)
                if isinstance(parsed, PathSelector) or not parsed.upstream:
                    continue
                if parsed.kind not in {SelectorKind.NAME, SelectorKind.SOURCE}:
                    continue
                key: CompiledObjectKey | None = all_keys.get(parsed.value)
                if key is not None and key.resource_type == CompiledResourceType.SOURCE:
                    keys.add(key)
    return frozenset(key for key in keys if key in selected_keys)
