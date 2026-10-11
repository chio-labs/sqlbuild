"""Canonical scope lookups, ordered and grouped by the native scope lookup."""

from __future__ import annotations

from collections.abc import Callable, Hashable, Sequence
from types import MappingProxyType

import sqlbuild._native as _native
from sqlbuild.compiler.scopes._helpers.placement import qualified_row, root_row
from sqlbuild.compiler.scopes.exceptions import InvalidScopePathError
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationRecord,
    DeclarationVisibilityIndex,
    GrantRecord,
    ResourceIdentity,
    ResourceRecord,
    ScopeIndex,
    ScopeLookup,
    UsageRecord,
)
from sqlbuild.compiler.scopes.types import ResourceKind

type _Groups = list[list[int]]
type _Mappings = tuple[_Groups, _Groups, _Groups, _Groups, _Groups, _Groups, list[str]]
type _Visibility = tuple[
    list[int],
    list[tuple[tuple[str, str], list[int]]],
    list[tuple[str, list[int]]],
    list[tuple[str, list[int]]],
]


def build_lookup(*, index: ScopeIndex) -> ScopeLookup:
    """The native lookup of `index`; a path the lookup rejects raises `InvalidScopePathError`."""

    native: _native.NativeScopeLookup | None
    native, (rows, error) = _native.build_native_scope_lookup(
        (
            [root_row(root=root) for root in index.ownership_roots],
            [
                (
                    (record.identity.kind.value, record.identity.name),
                    record.path,
                    root_row(root=record.ownership_root),
                )
                for record in index.resources
            ],
            [
                (
                    qualified_row(identity=record.identity),
                    record.path,
                    record.line,
                    record.column,
                    record.scope.value,
                    root_row(root=record.ownership_root),
                    record.owning_path,
                )
                for record in index.declarations
            ],
            [
                (
                    qualified_row(identity=usage.consumer),
                    qualified_row(identity=usage.declaration),
                    usage.kind.value,
                    None if usage.through is None else qualified_row(identity=usage.through),
                )
                for usage in index.usages
            ],
            [
                (
                    (grant.resource.kind.value, grant.resource.name),
                    qualified_row(identity=grant.declaration),
                    qualified_row(identity=grant.through),
                    grant.kind.value,
                )
                for grant in index.grants
            ],
            [(item.path, item.line, item.column, item.code.value) for item in index.diagnostics],
        )
    )
    if rows is None:
        raise InvalidScopePathError(error or "")
    (roots, resources, declarations, usages, grants, diagnostics), mappings, visibility = rows
    canonical: ScopeIndex = ScopeIndex(
        ownership_roots=tuple(index.ownership_roots[position] for position in roots),
        resources=tuple(index.resources[position] for position in resources),
        declarations=tuple(index.declarations[position] for position in declarations),
        usages=tuple(index.usages[position] for position in usages),
        grants=tuple(index.grants[position] for position in grants),
        visibility=index.visibility,
        inaccessible=index.inaccessible,
        diagnostics=tuple(index.diagnostics[position] for position in diagnostics),
        completeness=index.completeness,
    )
    return project_lookup(
        index=canonical,
        records=(index.resources, index.declarations, index.usages, index.grants),
        mappings=mappings,
        visibility=visibility,
        native=native,
    )


def project_lookup(
    *,
    index: ScopeIndex,
    records: tuple[
        Sequence[ResourceRecord],
        Sequence[DeclarationRecord],
        Sequence[UsageRecord],
        Sequence[GrantRecord],
    ],
    mappings: _Mappings,
    visibility: _Visibility,
    native: object | None,
) -> ScopeLookup:
    """Project native lookup groups over `records` as a `ScopeLookup` of canonical `index`."""

    resources, declarations, usages, grants = records
    global_positions, private_positions, local_positions, inherited_positions = visibility
    return ScopeLookup(
        index=index,
        resources=_mapping(groups=mappings[0], records=resources, key=_resource_identity),
        resources_by_path=_path_mapping(groups=mappings[1], records=resources, paths=mappings[6]),
        declarations=_mapping(groups=mappings[2], records=declarations, key=_declaration_identity),
        usages_by_consumer=_mapping(groups=mappings[3], records=usages, key=_usage_consumer),
        usages_by_declaration=_mapping(groups=mappings[4], records=usages, key=_usage_declaration),
        grants_by_resource=_mapping(groups=mappings[5], records=grants, key=_grant_resource),
        visibility_index=DeclarationVisibilityIndex(
            identities=tuple(record.identity for record in index.declarations),
            global_positions=tuple(global_positions),
            private_positions=MappingProxyType(
                {
                    ResourceIdentity(ResourceKind(kind), name): tuple(positions)
                    for (kind, name), positions in private_positions
                }
            ),
            local_positions=MappingProxyType(
                {owner: tuple(positions) for owner, positions in local_positions}
            ),
            inherited_positions=MappingProxyType(
                {owner: tuple(positions) for owner, positions in inherited_positions}
            ),
        ),
        native=native,
    )


def _resource_identity(record: ResourceRecord) -> ResourceIdentity:
    return record.identity


def _declaration_identity(record: DeclarationRecord) -> DeclarationIdentity:
    return record.identity


def _usage_consumer(record: UsageRecord) -> ResourceIdentity | DeclarationIdentity:
    return record.consumer


def _usage_declaration(record: UsageRecord) -> DeclarationIdentity:
    return record.declaration


def _grant_resource(record: GrantRecord) -> ResourceIdentity:
    return record.resource


def _path_mapping(
    *, groups: _Groups, records: Sequence[ResourceRecord], paths: list[str]
) -> MappingProxyType[str, tuple[ResourceRecord, ...]]:
    items: list[tuple[str, tuple[ResourceRecord, ...]]] = []
    for group in groups:
        items.append((paths[group[0]], tuple(records[member] for member in group)))
    return MappingProxyType(dict(items))


def _mapping[Record, Key: Hashable](
    *, groups: _Groups, records: Sequence[Record], key: Callable[[Record], Key]
) -> MappingProxyType[Key, tuple[Record, ...]]:
    items: list[tuple[Key, tuple[Record, ...]]] = []
    for group in groups:
        grouped: tuple[Record, ...] = tuple(records[member] for member in group)
        items.append((key(grouped[0]), grouped))
    return MappingProxyType(dict(items))
