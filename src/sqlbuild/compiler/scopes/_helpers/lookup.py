"""Canonical scope lookup construction implementation."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Hashable, Iterable
from types import MappingProxyType

from sqlbuild.compiler.scopes._helpers.identities import format_identity
from sqlbuild.compiler.scopes._helpers.paths import normalize_path
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationRecord,
    GrantRecord,
    InaccessibleRecord,
    ResourceIdentity,
    ResourceRecord,
    ScopeIndex,
    ScopeLookup,
    UsageRecord,
    VisibilityRecord,
)


def group_records[Record, Key: Hashable](
    *,
    records: Iterable[Record],
    key: Callable[[Record], Key],
    sort_key: Callable[[Record], tuple[str, ...]],
) -> MappingProxyType[Key, tuple[Record, ...]]:
    grouped: dict[Key, list[Record]] = defaultdict(list)
    for record in records:
        grouped[key(record)].append(record)
    return MappingProxyType(
        {
            group_key: tuple(sorted(values, key=sort_key))
            for group_key, values in sorted(grouped.items(), key=lambda item: repr(item[0]))
        }
    )


def build_lookup(*, index: ScopeIndex) -> ScopeLookup:
    resources: list[ResourceRecord] = sorted(index.resources, key=resource_sort_key)
    declarations: list[DeclarationRecord] = sorted(index.declarations, key=declaration_sort_key)
    resource_map: MappingProxyType[ResourceIdentity, tuple[ResourceRecord, ...]] = group_records(
        records=resources,
        key=lambda item: item.identity,
        sort_key=resource_sort_key,
    )
    declaration_map: MappingProxyType[DeclarationIdentity, tuple[DeclarationRecord, ...]] = (
        group_records(
            records=declarations,
            key=lambda item: item.identity,
            sort_key=declaration_sort_key,
        )
    )

    paths: list[tuple[str, ResourceRecord]] = []
    for record in resources:
        path: str = normalize_path(path=record.path)
        paths.append((path, record))
    path_map: MappingProxyType[str, tuple[tuple[str, ResourceRecord], ...]] = group_records(
        records=paths,
        key=lambda item: item[0],
        sort_key=lambda item: resource_sort_key(item[1]),
    )

    canonical_index: ScopeIndex = ScopeIndex(
        resources=tuple(resources),
        declarations=tuple(declarations),
        usages=tuple(sorted(index.usages, key=usage_sort_key)),
        grants=tuple(sorted(index.grants, key=grant_sort_key)),
        visibility=tuple(sorted(index.visibility, key=visibility_sort_key)),
        inaccessible=tuple(sorted(index.inaccessible, key=inaccessible_sort_key)),
        diagnostics=tuple(
            sorted(
                index.diagnostics,
                key=lambda item: (
                    item.path or "",
                    item.line or 0,
                    item.column or 0,
                    item.code.value,
                ),
            )
        ),
        completeness=index.completeness,
    )
    resources_by_path: dict[str, tuple[ResourceRecord, ...]] = {}
    for path, records_for_path in path_map.items():
        resources_by_path[path] = tuple(item[1] for item in records_for_path)
    return ScopeLookup(
        index=canonical_index,
        resources=resource_map,
        resources_by_path=MappingProxyType(resources_by_path),
        declarations=declaration_map,
        usages_by_consumer=group_records(
            records=canonical_index.usages, key=lambda item: item.consumer, sort_key=usage_sort_key
        ),
        usages_by_declaration=group_records(
            records=canonical_index.usages,
            key=lambda item: item.declaration,
            sort_key=usage_sort_key,
        ),
        grants_by_resource=group_records(
            records=canonical_index.grants,
            key=lambda item: item.resource,
            sort_key=grant_sort_key,
        ),
        visibility_by_resource=group_records(
            records=canonical_index.visibility,
            key=lambda item: item.resource,
            sort_key=visibility_sort_key,
        ),
        inaccessible_by_resource=group_records(
            records=canonical_index.inaccessible,
            key=lambda item: item.resource,
            sort_key=inaccessible_sort_key,
        ),
    )


def identity_key(identity: ResourceIdentity | DeclarationIdentity) -> str:
    return format_identity(identity=identity)


def resource_sort_key(record: ResourceRecord) -> tuple[str, ...]:
    return (identity_key(record.identity), normalize_path(path=record.path))


def declaration_sort_key(record: DeclarationRecord) -> tuple[str, ...]:
    return (
        identity_key(record.identity),
        normalize_path(path=record.path),
        str(record.line),
        str(record.column),
    )


def usage_sort_key(record: UsageRecord) -> tuple[str, ...]:
    return (identity_key(record.consumer), identity_key(record.declaration), record.kind.value)


def grant_sort_key(record: GrantRecord) -> tuple[str, ...]:
    return (
        identity_key(record.resource),
        identity_key(record.declaration),
        identity_key(record.through),
        record.kind.value,
    )


def visibility_sort_key(record: VisibilityRecord) -> tuple[str, ...]:
    return (
        identity_key(record.resource),
        identity_key(record.declaration),
        record.reason.value,
        identity_key(record.through) if record.through else "",
    )


def inaccessible_sort_key(record: InaccessibleRecord) -> tuple[str, ...]:
    return (
        identity_key(record.resource),
        identity_key(record.declaration),
        record.reason.value,
    )
