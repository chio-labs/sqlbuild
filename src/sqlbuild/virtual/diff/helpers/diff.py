"""Virtual diff helper functions."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.main.selection import resolve_project_selectors
from sqlbuild.virtual.executor.main.rewrite import rewrite_virtual_project_model_locations
from sqlbuild.virtual.planner.main.targets import build_virtual_destination_from_physical_relation
from sqlbuild.virtual.state.models import (
    PhysicalRelationRecord,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentRecord,
)
from sqlbuild.virtual.state.types import VirtualEnvironmentStatus


def resolve_virtual_diff_model_names(
    *, graph: ProjectGraph, select: tuple[str, ...], exclude: tuple[str, ...]
) -> tuple[str, ...]:
    """Resolve model names selected for virtual diff."""

    if not select:
        return tuple(model.name for model in graph.project.models)
    selected_keys: frozenset[CompiledObjectKey] = resolve_project_selectors(
        select=select,
        exclude=exclude,
        all_keys=graph.all_keys,
        upstream_deps=graph.upstream_deps,
        downstream_deps=graph.downstream_deps,
        tag_index=graph.tag_index,
        path_index=graph.path_index,
    )
    return tuple(
        sorted(key.name for key in selected_keys if key.resource_type == CompiledResourceType.MODEL)
    )


def read_physical_relations_for_refs(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    refs: tuple[VirtualEnvironmentModelRefRecord, ...],
) -> dict[str, PhysicalRelationRecord]:
    """Read tracked physical relations for VDE refs."""

    relations: dict[str, PhysicalRelationRecord] = {}
    for ref in refs:
        relation: PhysicalRelationRecord | None = backend.get_physical_relation(
            state_connection,
            schema=schema,
            model_name=ref.model_name,
            version_hash=ref.version_hash,
        )
        if relation is not None:
            relations[ref.model_name] = relation
    return relations


def filter_models_with_changed_virtual_refs(
    *,
    selected_names: tuple[str, ...],
    from_refs: tuple[VirtualEnvironmentModelRefRecord, ...],
    to_refs: tuple[VirtualEnvironmentModelRefRecord, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split selected models into changed/missing refs and identical refs."""

    from_hashes: dict[str, str] = {ref.model_name: ref.version_hash for ref in from_refs}
    to_hashes: dict[str, str] = {ref.model_name: ref.version_hash for ref in to_refs}
    changed_names: list[str] = []
    skipped_names: list[str] = []
    for name in selected_names:
        from_hash: str | None = from_hashes.get(name)
        to_hash: str | None = to_hashes.get(name)
        if from_hash is not None and from_hash == to_hash:
            skipped_names.append(name)
        else:
            changed_names.append(name)
    return tuple(changed_names), tuple(skipped_names)


def rewrite_project_to_physical_relations(
    *, adapter: BaseAdapter, project: CompiledProject, relations: dict[str, PhysicalRelationRecord]
) -> CompiledProject:
    """Rewrite a project's model locations to tracked physical relations."""

    targets: dict[str, CompiledRelationLocation] = {
        model.name: build_virtual_destination_from_physical_relation(
            adapter=adapter,
            relation=relations[model.name],
            fallback_target=model.destination,
        )
        for model in project.models
        if model.name in relations
    }
    return rewrite_virtual_project_model_locations(project=project, rewritten_locations=targets)


def non_finalized_target_names(
    environments: tuple[tuple[str, VirtualEnvironmentRecord | None], ...],
) -> tuple[str, ...]:
    return tuple(
        name
        for name, environment in environments
        if environment is None or environment.status != VirtualEnvironmentStatus.FINALIZED
    )


def is_working_environment(environment: VirtualEnvironmentRecord | None) -> bool:
    return environment is None or environment.status != VirtualEnvironmentStatus.FINALIZED
