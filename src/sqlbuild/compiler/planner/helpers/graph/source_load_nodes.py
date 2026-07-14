"""Planner helpers for executable source-load nodes."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.helpers.graph.loader_dag import (
    build_intermediate_source_map,
    build_upstream_intermediate_source_map,
)
from sqlbuild.compiler.planner.models import SourceLoadPlanEntry
from sqlbuild.runtime.contracts.types import ExecutionResourceKind
from sqlbuild.spec.contracts.models import SourceEntry


def build_source_load_map(
    *, project: CompiledProject, selected_keys: frozenset[CompiledObjectKey]
) -> dict[str, SourceEntry]:
    """Return source entries available to source-load and source-read planning."""

    source_map: dict[str, SourceEntry] = {
        source.source_entry.name: source.source_entry for source in project.sources
    }
    source_map.update(build_intermediate_source_map(project=project, selected_keys=selected_keys))
    source_map.update(
        build_upstream_intermediate_source_map(project=project, selected_keys=selected_keys)
    )
    return source_map


def build_source_load_entries(
    *,
    execution_order: tuple[CompiledObjectKey, ...],
    selected_keys: frozenset[CompiledObjectKey],
    source_map: dict[str, SourceEntry],
    is_reload: bool,
) -> tuple[SourceLoadPlanEntry, ...]:
    """Return executable source-load plan entries in DAG execution order."""

    entries: list[SourceLoadPlanEntry] = []
    key: CompiledObjectKey
    for key in execution_order:
        if key not in selected_keys:
            continue
        if key.resource_type != CompiledResourceType.SOURCE:
            continue
        source_entry: SourceEntry | None = source_map.get(key.name)
        if source_entry is None or source_entry.loader is None:
            continue
        entries.append(
            SourceLoadPlanEntry(
                key=key,
                name=source_entry.name,
                loader=source_entry.loader,
                destination=source_entry.table or source_entry.name,
                resource_kind=_source_load_resource_kind(source_entry),
                write_strategy=source_entry.write_strategy,
                cursor_column=source_entry.cursor_column,
                unique_key=source_entry.unique_key,
                is_reload=is_reload,
                integration_kind=(
                    source_entry.integration_loader.kind
                    if source_entry.integration_loader is not None
                    else None
                ),
            )
        )
    return tuple(entries)


def _source_load_resource_kind(source_entry: SourceEntry) -> ExecutionResourceKind:
    return (
        ExecutionResourceKind.LOADER
        if source_entry.meta.get("sqlbuild_loader_node") is True
        else ExecutionResourceKind.SOURCE
    )
