"""Canonical model selector resolution for lint and format CLI commands."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.runtime.adapters import resolve_adapter
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs, DiscoveredSqlModelFile
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.main.selection.selection import resolve_project_selectors
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)

_GRAPH_SELECTOR_MARKERS: tuple[str, ...] = ("+", ":", "~", "/", "\\", ",")


def resolve_lint_inputs(
    *, project_dir: Path, select: tuple[str, ...], exclude: tuple[str, ...]
) -> tuple[BaseAdapter, frozenset[Path] | None, DiscoveredProjectInputs]:
    """Resolve the adapter and optional model-file scope through canonical selectors."""

    discovered: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=project_dir,
        sql_analysis_enabled_override=False,
        extract_output_column_locations=False,
    )
    adapter: BaseAdapter = resolve_adapter(
        adapter_name=resolve_effective_adapter_name(
            project_config=discovered.project_config,
            local_config=discovered.local_config,
        ),
        project_dir=project_dir,
    )
    if not select and not exclude:
        return adapter, None, discovered
    exact_paths: frozenset[Path] | None = _resolve_exact_model_paths(
        project_dir=project_dir,
        discovered=discovered,
        select=select,
        exclude=exclude,
    )
    if exact_paths is not None:
        _validate_selected_paths(paths=exact_paths)
        return adapter, exact_paths, discovered
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
    _validate_selected_paths(paths=paths)
    return adapter, paths, discovered


def _resolve_exact_model_paths(
    *,
    project_dir: Path,
    discovered: DiscoveredProjectInputs,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
) -> frozenset[Path] | None:
    """Resolve unexpanded model-name selectors without compiling the project graph."""

    model_names_and_paths: list[tuple[str, Path]] = []
    model_file: DiscoveredSqlModelFile
    for model_file in discovered.model_files:
        configured_name: object = model_file.header_values.get("name")
        model_name: str = (
            configured_name
            if isinstance(configured_name, str) and configured_name
            else model_file.relative_path.stem
        )
        model_names_and_paths.append(
            (model_name, (project_dir / model_file.relative_path).resolve())
        )
    selected_names: frozenset[str] | None = _exact_names(raw_selectors=select)
    excluded_names: frozenset[str] | None = _exact_names(raw_selectors=exclude)
    if selected_names is None or excluded_names is None:
        return None
    available_names: frozenset[str] = frozenset(name for name, _path in model_names_and_paths)
    unknown_names: frozenset[str] = (selected_names | excluded_names) - available_names
    if unknown_names:
        unknown_name: str = sorted(unknown_names)[0]
        raise PlannerInputError(f"unknown selector name '{unknown_name}'", code="S007")
    names: frozenset[str] = selected_names or available_names
    return frozenset(
        path for name, path in model_names_and_paths if name in names and name not in excluded_names
    )


def _exact_names(*, raw_selectors: tuple[str, ...]) -> frozenset[str] | None:
    """Return plain model names, or None when canonical graph resolution is required."""

    names: set[str] = set()
    raw_selector: str
    for raw_selector in raw_selectors:
        if not raw_selector.strip():
            return None
        token: str
        for token in raw_selector.split():
            if any(marker in token for marker in _GRAPH_SELECTOR_MARKERS):
                return None
            names.add(token)
    return frozenset(names)


def _validate_selected_paths(*, paths: frozenset[Path]) -> None:
    """Reject lint selections that contain no SQL model files."""

    if not paths:
        raise PlannerInputError(
            "lint selection matched no SQL model files",
            code="S007",
        )
