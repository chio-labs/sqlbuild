"""Canonical model selector resolution for lint and format CLI commands."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.runtime.adapters import resolve_adapter
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.main.selection.selection import resolve_project_selectors
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)


def resolve_lint_inputs(
    *, project_dir: Path, select: tuple[str, ...], exclude: tuple[str, ...]
) -> tuple[BaseAdapter, frozenset[Path] | None]:
    """Resolve the adapter and optional model-file scope through canonical selectors."""

    discovered: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=project_dir,
        sql_analysis_enabled_override=False,
    )
    adapter: BaseAdapter = resolve_adapter(
        adapter_name=resolve_effective_adapter_name(
            project_config=discovered.project_config,
            local_config=discovered.local_config,
        ),
        project_dir=project_dir,
    )
    if not select and not exclude:
        return adapter, None
    graph: ProjectGraph = build_project_graph(discovered_inputs=discovered, adapter=adapter)
    selected_keys: frozenset[CompiledObjectKey] = resolve_project_selectors(
        select=select,
        exclude=exclude,
        all_keys=graph.all_keys,
        upstream_deps=graph.upstream_deps,
        downstream_deps=graph.downstream_deps,
        tag_index=graph.tag_index,
        path_index=graph.path_index,
    )
    selected_names: frozenset[str] = frozenset(
        key.name for key in selected_keys if key.resource_type == CompiledResourceType.MODEL
    )
    paths: frozenset[Path] = frozenset(
        (project_dir / model.relative_path).resolve()
        for model in graph.project.models
        if model.name in selected_names
    )
    if (select or exclude) and not paths:
        raise PlannerInputError(
            "lint selection matched no SQL model files",
            code="S007",
        )
    return adapter, paths
