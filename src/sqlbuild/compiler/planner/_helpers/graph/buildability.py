"""Buildability validation for selected scope against warehouse state."""

from __future__ import annotations

from sqlbuild.adapter.models import RelationInfo
from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import MissingUpstream, WarehouseSnapshot


def check_buildability(
    *,
    selected_keys: frozenset[CompiledObjectKey],
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    snapshot: WarehouseSnapshot,
    deferred_relations: dict[str, RelationInfo] | None = None,
    satisfied_keys: frozenset[CompiledObjectKey] = frozenset(),
) -> tuple[MissingUpstream, ...]:
    """Validate that all upstream deps for selected keys exist in scope or warehouse."""

    missing_map: dict[CompiledObjectKey, list[CompiledObjectKey]] = {}

    selected_key: CompiledObjectKey
    for selected_key in selected_keys:
        dep_keys: tuple[CompiledObjectKey, ...] = upstream_deps.get(selected_key, ())
        dep_key: CompiledObjectKey
        for dep_key in dep_keys:
            if dep_key.resource_type == CompiledResourceType.SQL_TEST:
                continue
            if dep_key.resource_type == CompiledResourceType.DBT_REF:
                continue
            if dep_key.resource_type == CompiledResourceType.SOURCE:
                continue
            if dep_key in selected_keys:
                continue
            if dep_key in satisfied_keys:
                continue
            if dep_key.name in snapshot.existing_relations:
                continue
            if deferred_relations is not None and dep_key.name in deferred_relations:
                continue
            missing_map.setdefault(dep_key, []).append(selected_key)

    missing: list[MissingUpstream] = [
        MissingUpstream(
            key=key,
            required_by=tuple(sorted(dependents, key=lambda k: (k.resource_type, k.name))),
        )
        for key, dependents in sorted(
            missing_map.items(),
            key=lambda item: (-len(item[1]), item[0].resource_type, item[0].name),
        )
    ]

    return tuple(missing)
