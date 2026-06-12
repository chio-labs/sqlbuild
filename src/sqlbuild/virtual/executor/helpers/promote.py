"""Virtual promote helper functions."""

from __future__ import annotations

from typing import Any

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.virtual.state.models import PhysicalRelationRecord, VirtualEnvironmentSeedRefRecord
from sqlbuild.virtual.state.types import PhysicalArtifactType


def read_seed_physical_relations(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    refs: tuple[VirtualEnvironmentSeedRefRecord, ...],
) -> dict[str, PhysicalRelationRecord]:
    relations: dict[str, PhysicalRelationRecord] = {}
    for ref in refs:
        relation: PhysicalRelationRecord | None = backend.get_physical_relation_for_artifact(
            state_connection,
            schema=schema,
            artifact_type=PhysicalArtifactType.SEED,
            artifact_name=ref.seed_name,
            version_hash=ref.version_hash,
        )
        if relation is not None:
            relations[ref.seed_name] = relation
    return relations


def selected_upstream_seed_names(
    *,
    graph: ProjectGraph,
    selected_model_names: tuple[str, ...],
    all_seed_names: tuple[str, ...],
    include_all: bool,
) -> tuple[str, ...]:
    if include_all:
        return all_seed_names
    selected: set[str] = set()
    pending: list[CompiledObjectKey] = [
        model.key for model in graph.project.models if model.name in selected_model_names
    ]
    seen: set[CompiledObjectKey] = set()
    while pending:
        key: CompiledObjectKey = pending.pop()
        if key in seen:
            continue
        seen.add(key)
        for upstream_key in graph.upstream_deps.get(key, ()):
            if upstream_key.resource_type == CompiledResourceType.SEED:
                selected.add(upstream_key.name)
                continue
            pending.append(upstream_key)
    return tuple(sorted(selected))
