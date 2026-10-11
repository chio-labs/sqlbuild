"""Validate declaration usage and exact lexical placement with the native placement rules."""

from __future__ import annotations

from dataclasses import replace

import sqlbuild._native as _native
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationRecord,
    OwnershipRoot,
    ResourceIdentity,
    ScopeDiagnostic,
    ScopeIndex,
    UsageRecord,
)
from sqlbuild.compiler.scopes.types import (
    DeclarationKind,
    DiagnosticSeverity,
    NativePlacementRows,
    NativeQualifiedRow,
    NativeRootRow,
    NativeUsageKeyRow,
    OwnershipRootKind,
    ResourceKind,
    ScopeDiagnosticCode,
    ScopeKind,
)

_PLACEMENT_CODES: frozenset[ScopeDiagnosticCode] = frozenset(
    {
        ScopeDiagnosticCode.UNUSED_DECLARATION,
        ScopeDiagnosticCode.LOCAL_NEEDED_BY_DESCENDANT,
        ScopeDiagnosticCode.OVER_BROAD_INHERITED,
        ScopeDiagnosticCode.REQUIRES_GLOBAL_PLACEMENT,
        ScopeDiagnosticCode.OVER_BROAD_GLOBAL,
    }
)


def merged_usage_index(*, index: ScopeIndex, collected: tuple[UsageRecord, ...]) -> ScopeIndex:
    """The index with compile usages merged into its usages and macro dependencies."""

    distinct, merged, combined = _native.scope_merged_usages(
        [_dependency_row(record=record) for record in index.declarations],
        [_usage_row(usage=usage) for usage in index.usages],
        [_usage_row(usage=usage) for usage in collected],
    )
    usages: list[UsageRecord] = [collected[position] for position in distinct]
    all_usages: list[UsageRecord] = [*index.usages, *usages]
    return replace(
        index,
        declarations=tuple(
            _with_dependencies(record=record, sources=sources, usages=usages)
            for record, sources in zip(index.declarations, merged, strict=True)
        ),
        usages=tuple(all_usages[position] for position in combined),
        completeness=replace(index.completeness, runtime_usage=True, promotion_impact=True),
    )


def _dependency_row(
    *, record: DeclarationRecord
) -> tuple[NativeQualifiedRow, list[NativeQualifiedRow] | None]:
    dependencies: tuple[DeclarationIdentity, ...] | None = (
        None if record.macro is None else record.macro.dependencies
    )
    return (
        qualified_row(identity=record.identity),
        None if dependencies is None else [qualified_row(identity=item) for item in dependencies],
    )


def _with_dependencies(
    *,
    record: DeclarationRecord,
    sources: list[tuple[bool, int]] | None,
    usages: list[UsageRecord],
) -> DeclarationRecord:
    if record.macro is None or sources is None:
        return record
    own: tuple[DeclarationIdentity, ...] = record.macro.dependencies
    return replace(
        record,
        macro=replace(
            record.macro,
            dependencies=tuple(
                own[position] if is_own else usages[position].declaration
                for is_own, position in sources
            ),
        ),
    )


def _usage_row(*, usage: UsageRecord) -> NativeUsageKeyRow:
    return (
        qualified_row(identity=usage.consumer),
        qualified_row(identity=usage.declaration),
        usage.kind.value,
        None if usage.through is None else qualified_row(identity=usage.through),
        usage.enum_member,
    )


def build_placement_validated_index(
    *, index: ScopeIndex, enforce_placement: bool = True
) -> ScopeIndex:
    """Return the index with deterministic unused and exact-placement diagnostics."""

    kept: list[ScopeDiagnostic] = [
        item for item in index.diagnostics if item.code not in _PLACEMENT_CODES
    ]
    if not index.completeness.runtime_usage:
        return replace(
            index,
            diagnostics=tuple(kept),
            completeness=replace(index.completeness, placement=False),
        )
    severity: DiagnosticSeverity = (
        DiagnosticSeverity.ERROR if enforce_placement else DiagnosticSeverity.WARNING
    )
    for position, code, message in _native.scope_placement_diagnostics(_rows(index=index)):
        declaration: DeclarationRecord = index.declarations[position]
        kept.append(
            ScopeDiagnostic(
                code=ScopeDiagnosticCode(code),
                message=message,
                path=declaration.path,
                line=declaration.line,
                column=declaration.column,
                declaration=declaration.identity,
                severity=severity,
            )
        )
    return replace(
        index,
        diagnostics=tuple(sorted(kept, key=_diagnostic_key)),
        completeness=replace(index.completeness, placement=True),
    )


def declaration_directory(*, kind: DeclarationKind, scope: ScopeKind, path: str | None) -> str:
    """Return the project-relative folder where a declaration with this placement lives."""

    return _native.scope_declaration_directory(kind.value, scope.value, path)


def relocate_for_resource_move(
    *, index: ScopeIndex, resource: ResourceIdentity, destination: str
) -> tuple[DeclarationRecord, ...] | None:
    """Return declarations whose placement changes when a resource moves, or None if unsettled."""

    if not index.completeness.runtime_usage:
        return None
    relocations: list[tuple[int, str, str, NativeRootRow, str | None]] | None = (
        _native.scope_relocations(
            _rows(index=index), (resource.kind.value, resource.name), destination
        )
    )
    if relocations is None:
        return None
    return tuple(
        replace(
            index.declarations[position],
            path=path,
            scope=ScopeKind(scope),
            ownership_root=OwnershipRoot(
                root_path,
                OwnershipRootKind(root_kind),
                None if resource_kind is None else ResourceKind(resource_kind),
            ),
            owning_path=owning_path,
        )
        for position, path, scope, (root_path, root_kind, resource_kind), owning_path in (
            relocations
        )
    )


def _rows(*, index: ScopeIndex) -> NativePlacementRows:
    return (
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
                None if usage.through is None else qualified_row(identity=usage.through),
            )
            for usage in index.usages
        ],
    )


def qualified_row(*, identity: ResourceIdentity | DeclarationIdentity) -> NativeQualifiedRow:
    if isinstance(identity, ResourceIdentity) or identity.owner is None:
        return identity.kind.value, identity.name, None
    return (
        identity.kind.value,
        identity.name,
        (identity.owner.kind.value, identity.owner.name),
    )


def root_row(*, root: OwnershipRoot) -> NativeRootRow:
    return (
        root.path,
        root.kind.value,
        None if root.resource_kind is None else root.resource_kind.value,
    )


def _diagnostic_key(item: ScopeDiagnostic) -> tuple[str, int, int, str, str]:
    return (item.path or "", item.line or 0, item.column or 0, item.code.value, item.message)
