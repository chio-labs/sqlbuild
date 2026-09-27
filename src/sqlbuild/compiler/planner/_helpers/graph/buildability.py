"""Buildability validation for selected scope against warehouse state."""

from __future__ import annotations

from sqlbuild.adapter.contract.models import RelationInfo
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import MissingUpstream, WarehouseSnapshot

_MESSAGE_ITEM_LIMIT: int = 5


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


def missing_upstream_message(
    *,
    missing: tuple[MissingUpstream, ...],
    edge_origins: dict[tuple[CompiledObjectKey, CompiledObjectKey], str],
) -> str:
    """Describe missing upstream keys, naming the audit when only an audit read requires one."""

    lineage_missing: list[MissingUpstream] = []
    audit_reads: dict[str, None] = {}
    entry: MissingUpstream
    for entry in missing:
        origins: tuple[str, ...] = tuple(
            edge_origins[(dependent, entry.key)]
            for dependent in entry.required_by
            if (dependent, entry.key) in edge_origins
        )
        if len(origins) < len(entry.required_by):
            lineage_missing.append(entry)
            continue
        audit_reads.update(dict.fromkeys(origins))
    parts: list[str] = []
    if lineage_missing:
        names: str = ", ".join(m.key.name for m in lineage_missing[:_MESSAGE_ITEM_LIMIT])
        parts.append(f"{len(lineage_missing)} missing upstream dependencies ({names})")
    read_names: tuple[str, ...] = tuple(audit_reads)
    if len(read_names) == 1:
        parts.append(
            f"{read_names[0]}, which is not selected and does not exist in the warehouse; "
            "select it or build it first"
        )
    elif read_names:
        shown: str = "; ".join(read_names[:_MESSAGE_ITEM_LIMIT])
        more: str = "; ..." if len(read_names) > _MESSAGE_ITEM_LIMIT else ""
        parts.append(
            f"{len(read_names)} audit reads are not selected and do not exist in the warehouse "
            f"({shown}{more}); select them or build them first"
        )
    return "cannot build selected scope: " + "; ".join(parts)
