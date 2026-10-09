"""A natively built scope index, materialised as the Python scope models it replaces."""

from __future__ import annotations

from collections.abc import Callable, Hashable, Sequence
from dataclasses import replace
from types import MappingProxyType

import sqlbuild._native as _native
from sqlbuild.compiler.scopes.classes.native_scope_rows import NativeScopeRows
from sqlbuild.compiler.scopes.exceptions import UnindexableScopeError
from sqlbuild.compiler.scopes.models import (
    DeclarationRecord,
    DeclarationVisibilityIndex,
    GrantRecord,
    NativeDeclarationValues,
    OwnershipRoot,
    RelationshipFact,
    ResourceIdentity,
    ResourceRecord,
    ScopeCompleteness,
    ScopeDiagnostic,
    ScopeIndex,
    ScopeLookup,
    UsageRecord,
)
from sqlbuild.compiler.scopes.types import (
    GrantKind,
    OwnershipRootKind,
    ResourceKind,
    ScopeDiagnosticCode,
    UsageKind,
)

type _Groups = tuple[list[list[int]], bool]
type _IndexRows = tuple[
    list[str],
    list[tuple[str, str, str, str | None, str | None]],
    list[int],
    list[int],
    list[tuple[int, int]],
    list[tuple[str, str, str | None, int | None, int | None, int | None, int | None]],
    bool,
]
type _GrantRows = list[tuple[str, str, int, str | int, str]]
type _LookupRows = tuple[
    list[int],
    list[int],
    list[int],
    list[int],
    tuple[_Groups, _Groups, _Groups, _Groups, _Groups, _Groups],
    tuple[
        list[int],
        list[tuple[tuple[str, str], list[int]]],
        list[tuple[str, list[int]]],
        list[tuple[str, list[int]]],
    ],
]

_RESOURCE_ROOTS: dict[ResourceKind, str] = {
    ResourceKind.MODEL: "models",
    ResourceKind.TEST: "tests/unit",
    ResourceKind.SCENARIO: "tests/scenarios",
    ResourceKind.FUNCTION: "functions/sql",
    ResourceKind.SOURCE: "sources",
}
_FIXED_ROOTS: dict[str, OwnershipRoot] = {
    "seed": OwnershipRoot("seeds", OwnershipRootKind.GLOBAL, ResourceKind.SEED),
    "python_function": OwnershipRoot(
        "functions/python", OwnershipRootKind.GLOBAL, ResourceKind.FUNCTION
    ),
}
_STATIC_COMPLETENESS: ScopeCompleteness = ScopeCompleteness(
    runtime_usage=False, relationships=False, placement=False, promotion_impact=False
)


class NativeScopeIndex:
    """One native scope index and the Python records materialised from it."""

    def __init__(self, *, native: _native.NativeScopeIndex, rows: NativeScopeRows) -> None:
        records: _IndexRows = native.records()
        paths, declaration_rows, resource_order, declaration_order, usages, diagnostics, scoped = (
            records
        )
        self._native: _native.NativeScopeIndex = native
        self._resources: list[ResourceRecord] = [
            ResourceRecord(
                identity=identity,
                path=path,
                ownership_root=_resource_root(identity=identity, root=root),
            )
            for identity, path, root in zip(
                rows.resource_identities, paths, rows.resource_roots, strict=True
            )
        ]
        self._declarations: list[DeclarationRecord] = [
            _declaration_record(values=values, row=row)
            for values, row in zip(rows.declaration_values, declaration_rows, strict=True)
        ]
        self._usages: list[UsageRecord] = [
            UsageRecord(
                consumer=self._declarations[consumer].identity,
                declaration=rows.declaration_values[consumer].dependencies[dependency],
                kind=UsageKind.DECLARATION_DEPENDENCY,
            )
            for consumer, dependency in usages
        ]
        self._grants: list[GrantRecord] = []
        self.has_scoped_relationship_declarations: bool = scoped
        self.index: ScopeIndex = ScopeIndex(
            ownership_roots=tuple(
                OwnershipRoot(path=path, resource_kind=kind)
                for kind, path in sorted(_RESOURCE_ROOTS.items(), key=lambda item: item[1])
            ),
            resources=tuple(self._resources[position] for position in resource_order),
            declarations=tuple(self._declarations[position] for position in declaration_order),
            usages=tuple(self._usages),
            diagnostics=tuple(
                ScopeDiagnostic(
                    ScopeDiagnosticCode(code),
                    message,
                    path=path,
                    line=line,
                    column=column,
                    declaration=(
                        None if declaration is None else self._declarations[declaration].identity
                    ),
                    resource=None if resource is None else self._resources[resource].identity,
                )
                for code, message, path, line, column, declaration, resource in diagnostics
            ),
            completeness=_STATIC_COMPLETENESS,
        )

    def grant(self, facts: Sequence[RelationshipFact]) -> None:
        """Attach the relationship grants of `facts`."""

        rows: _GrantRows | None = self._native.grant(
            [
                (
                    fact.resource.kind.value,
                    fact.resource.name,
                    list(fact.expected_models),
                    list(fact.called_macros),
                    list(fact.tested_macros),
                )
                for fact in facts
            ]
        )
        if rows is None:
            raise UnindexableScopeError
        identities: dict[tuple[str, str], ResourceIdentity] = {}
        self._grants = [
            GrantRecord(
                resource=identities.setdefault(
                    (kind, name), ResourceIdentity(ResourceKind(kind), name)
                ),
                declaration=self._declarations[declaration].identity,
                through=(
                    ResourceIdentity(ResourceKind.MODEL, through)
                    if isinstance(through, str)
                    else self._declarations[through].identity
                ),
                kind=GrantKind(grant_kind),
            )
            for kind, name, declaration, through, grant_kind in rows
        ]

    def index_with_relationships(self) -> ScopeIndex:
        """Return the index with its grants attached and relationships complete."""

        return replace(
            self.index,
            grants=tuple(self._grants),
            completeness=replace(self.index.completeness, relationships=True),
        )

    def lookup(self, *, index: ScopeIndex) -> ScopeLookup:
        """Return Python's `build_lookup(index)` for `index_with_relationships()`."""

        rows: _LookupRows | None = self._native.lookup()
        if rows is None:
            raise UnindexableScopeError
        resource_positions, declaration_positions, usage_positions, grant_positions = rows[:4]
        groups: tuple[_Groups, _Groups, _Groups, _Groups, _Groups, _Groups] = rows[4]
        global_positions, private_positions, local_positions, inherited_positions = rows[5]
        declarations: tuple[DeclarationRecord, ...] = tuple(
            self._declarations[position] for position in declaration_positions
        )
        canonical_index: ScopeIndex = ScopeIndex(
            ownership_roots=tuple(
                sorted(
                    index.ownership_roots,
                    key=lambda item: (
                        item.path,
                        item.resource_kind.value if item.resource_kind is not None else "",
                    ),
                )
            ),
            resources=tuple(self._resources[position] for position in resource_positions),
            declarations=declarations,
            usages=tuple(self._usages[position] for position in usage_positions),
            grants=tuple(self._grants[position] for position in grant_positions),
            visibility=(),
            inaccessible=(),
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
        return ScopeLookup(
            index=canonical_index,
            resources=_mapping(
                groups=groups[0], records=self._resources, key=lambda item: item.identity
            ),
            resources_by_path=_mapping(
                groups=groups[1], records=self._resources, key=lambda item: item.path
            ),
            declarations=_mapping(
                groups=groups[2], records=self._declarations, key=lambda item: item.identity
            ),
            usages_by_consumer=_mapping(
                groups=groups[3], records=self._usages, key=lambda item: item.consumer
            ),
            usages_by_declaration=_mapping(
                groups=groups[4], records=self._usages, key=lambda item: item.declaration
            ),
            grants_by_resource=_mapping(
                groups=groups[5], records=self._grants, key=lambda item: item.resource
            ),
            visibility_index=DeclarationVisibilityIndex(
                identities=tuple(declaration.identity for declaration in declarations),
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
        )


def _resource_root(*, identity: ResourceIdentity, root: str) -> OwnershipRoot:
    fixed: OwnershipRoot | None = _FIXED_ROOTS.get(root)
    if fixed is not None:
        return fixed
    return OwnershipRoot(path=_RESOURCE_ROOTS[identity.kind], resource_kind=identity.kind)


def _declaration_record(
    *, values: NativeDeclarationValues, row: tuple[str, str, str, str | None, str | None]
) -> DeclarationRecord:
    path, root_path, root_kind, root_resource_kind, owning_path = row
    return DeclarationRecord(
        identity=values.identity,
        path=path,
        line=values.line,
        column=1,
        scope=values.scope,
        ownership_root=OwnershipRoot(
            root_path,
            OwnershipRootKind(root_kind),
            None if root_resource_kind is None else ResourceKind(root_resource_kind),
        ),
        owning_path=owning_path,
        macro=values.macro,
        enum=values.enum,
        constant=values.constant,
    )


def _mapping[Record, Key: Hashable](
    *, groups: _Groups, records: Sequence[Record], key: Callable[[Record], Key]
) -> MappingProxyType[Key, tuple[Record, ...]]:
    members, repr_ordered = groups
    items: list[tuple[Key, tuple[Record, ...]]] = []
    for group in members:
        grouped: tuple[Record, ...] = tuple(records[member] for member in group)
        items.append((key(grouped[0]), grouped))
    if not repr_ordered:
        items.sort(key=lambda item: repr(item[0]))
    return MappingProxyType(dict(items))
