"""Validate declaration usage and exact lexical placement."""

from __future__ import annotations

from collections import deque
from dataclasses import replace
from pathlib import PurePosixPath

from sqlbuild.compiler.scopes._helpers.identities import format_identity
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationRecord,
    OwnershipRoot,
    ResourceIdentity,
    ResourceRecord,
    ScopeDiagnostic,
    ScopeIndex,
    UsageRecord,
)
from sqlbuild.compiler.scopes.types import ScopeDiagnosticCode, ScopeKind

type _Anchor = tuple[OwnershipRoot, str]
type _UsagesByDeclaration = dict[DeclarationIdentity, tuple[UsageRecord, ...]]
type _AnchorSets = dict[DeclarationIdentity, frozenset[_Anchor]]

_PLACEMENT_CODES: frozenset[ScopeDiagnosticCode] = frozenset(
    {
        ScopeDiagnosticCode.UNUSED_DECLARATION,
        ScopeDiagnosticCode.LOCAL_NEEDED_BY_DESCENDANT,
        ScopeDiagnosticCode.OVER_BROAD_INHERITED,
        ScopeDiagnosticCode.REQUIRES_GLOBAL_PLACEMENT,
        ScopeDiagnosticCode.OVER_BROAD_GLOBAL,
    }
)


def build_placement_validated_index(*, index: ScopeIndex) -> ScopeIndex:
    """Return the index with deterministic unused and exact-placement diagnostics."""

    if not index.completeness.runtime_usage:
        return replace(
            index,
            diagnostics=tuple(
                item for item in index.diagnostics if item.code not in _PLACEMENT_CODES
            ),
            completeness=replace(index.completeness, placement=False),
        )
    usages_by_declaration: _UsagesByDeclaration = _usages_by_declaration(index=index)
    anchor_sets: _AnchorSets = _anchor_sets(
        index=index, usages_by_declaration=usages_by_declaration
    )

    diagnostics: list[ScopeDiagnostic] = [
        item for item in index.diagnostics if item.code not in _PLACEMENT_CODES
    ]
    for declaration in index.declarations:
        declaration_usages: tuple[UsageRecord, ...] = usages_by_declaration.get(
            declaration.identity, ()
        )
        if declaration.scope is ScopeKind.PRIVATE:
            declaration_usages = tuple(
                usage
                for usage in declaration_usages
                if usage.consumer == declaration.identity.owner and usage.through is None
            )
        if not declaration_usages:
            diagnostics.append(
                _diagnostic(
                    declaration=declaration,
                    code=ScopeDiagnosticCode.UNUSED_DECLARATION,
                    message=f"Unused {declaration.scope.value} declaration "
                    f"'{format_identity(identity=declaration.identity)}' at {declaration.path}; "
                    "remove it or add a genuine runtime use",
                )
            )
            continue
        if declaration.scope is ScopeKind.PRIVATE:
            continue
        required: tuple[ScopeKind, str | None, tuple[str, ...]] | None = (
            _required_placement_for_record(
                record=declaration,
                usages_by_declaration=usages_by_declaration,
                anchor_sets=anchor_sets,
            )
        )
        if required is None:
            continue
        required_scope, required_path, consumer_labels = required
        consumers: str = ", ".join(consumer_labels)
        if declaration.scope is required_scope and declaration.owning_path == required_path:
            continue
        if required_scope is ScopeKind.GLOBAL:
            diagnostics.append(
                _diagnostic(
                    declaration=declaration,
                    code=ScopeDiagnosticCode.REQUIRES_GLOBAL_PLACEMENT,
                    message=_message(
                        declaration=declaration,
                        required_scope=ScopeKind.GLOBAL,
                        required_path=None,
                        consumers=consumers,
                    ),
                )
            )
            continue
        code: ScopeDiagnosticCode = (
            ScopeDiagnosticCode.LOCAL_NEEDED_BY_DESCENDANT
            if declaration.scope is ScopeKind.LOCAL
            else (
                ScopeDiagnosticCode.OVER_BROAD_GLOBAL
                if declaration.scope is ScopeKind.GLOBAL
                else ScopeDiagnosticCode.OVER_BROAD_INHERITED
            )
        )
        diagnostics.append(
            _diagnostic(
                declaration=declaration,
                code=code,
                message=_message(
                    declaration=declaration,
                    required_scope=required_scope,
                    required_path=required_path,
                    consumers=consumers,
                ),
            )
        )
    return replace(
        index,
        diagnostics=tuple(sorted(diagnostics, key=_diagnostic_key)),
        completeness=replace(index.completeness, placement=True),
    )


def resolve_required_placement(
    *, index: ScopeIndex, declaration: DeclarationIdentity
) -> tuple[ScopeKind, str | None, tuple[str, ...]] | None:
    """Return exact required placement using the validation anchor semantics."""

    records: tuple[DeclarationRecord, ...] = tuple(
        item for item in index.declarations if item.identity == declaration
    )
    if not records or not index.completeness.runtime_usage:
        return None
    usages_by_declaration: _UsagesByDeclaration = _usages_by_declaration(index=index)
    return _required_placement_for_record(
        record=records[0],
        usages_by_declaration=usages_by_declaration,
        anchor_sets=_anchor_sets(index=index, usages_by_declaration=usages_by_declaration),
    )


def _usages_by_declaration(*, index: ScopeIndex) -> _UsagesByDeclaration:
    usage_lists: dict[DeclarationIdentity, list[UsageRecord]] = {}
    for usage in index.usages:
        usage_lists.setdefault(usage.declaration, []).append(usage)
    return {identity: tuple(usages) for identity, usages in usage_lists.items()}


def _required_placement_for_record(
    *,
    record: DeclarationRecord,
    usages_by_declaration: _UsagesByDeclaration,
    anchor_sets: _AnchorSets,
) -> tuple[ScopeKind, str | None, tuple[str, ...]] | None:
    declaration: DeclarationIdentity = record.identity
    declaration_usages: tuple[UsageRecord, ...] = usages_by_declaration.get(declaration, ())
    if record.scope is ScopeKind.PRIVATE:
        direct_private: tuple[UsageRecord, ...] = tuple(
            usage
            for usage in declaration_usages
            if usage.consumer == declaration.owner and usage.through is None
        )
        return (
            (ScopeKind.PRIVATE, record.owning_path or record.ownership_root.path, ())
            if direct_private
            else None
        )
    if not declaration_usages:
        return None
    anchors: frozenset[_Anchor] = anchor_sets.get(declaration, frozenset())
    if not anchors:
        return None
    consumers: tuple[str, ...] = tuple(
        sorted({_consumer_label(usage) for usage in declaration_usages})
    )
    if len({root for root, _path in anchors}) != 1:
        return ScopeKind.GLOBAL, None, consumers
    paths: tuple[str, ...] = tuple(path for _root, path in anchors)
    distinct: set[str] = set(paths)
    if len(distinct) == 1:
        return ScopeKind.LOCAL, next(iter(distinct)), consumers
    return ScopeKind.INHERITED, _lca(paths), consumers


def _anchor_sets(*, index: ScopeIndex, usages_by_declaration: _UsagesByDeclaration) -> _AnchorSets:
    """Return each declaration's resource anchors reachable through consumer chains."""

    resources: dict[ResourceIdentity, ResourceRecord] = {
        item.identity: item for item in index.resources
    }
    anchors: dict[DeclarationIdentity, set[_Anchor]] = {}
    dependents: dict[DeclarationIdentity, set[DeclarationIdentity]] = {}
    for identity, declaration_usages in usages_by_declaration.items():
        direct: set[_Anchor] = anchors.setdefault(identity, set())
        for usage in declaration_usages:
            resource_identity: ResourceIdentity | None = usage.through
            if resource_identity is None and isinstance(usage.consumer, ResourceIdentity):
                resource_identity = usage.consumer
            if resource_identity is not None:
                resource: ResourceRecord | None = resources.get(resource_identity)
                if resource is not None:
                    direct.add(
                        (resource.ownership_root, PurePosixPath(resource.path).parent.as_posix())
                    )
                continue
            if isinstance(usage.consumer, DeclarationIdentity):
                dependents.setdefault(usage.consumer, set()).add(identity)
    pending: deque[DeclarationIdentity] = deque(anchors)
    while pending:
        source: DeclarationIdentity = pending.popleft()
        source_anchors: set[_Anchor] = anchors.get(source, set())
        for target in dependents.get(source, ()):
            target_anchors: set[_Anchor] = anchors.setdefault(target, set())
            if source_anchors <= target_anchors:
                continue
            target_anchors |= source_anchors
            pending.append(target)
    return {identity: frozenset(items) for identity, items in anchors.items()}


def _lca(paths: tuple[str, ...]) -> str:
    parts: list[tuple[str, ...]] = [PurePosixPath(path).parts for path in paths]
    common: list[str] = []
    for components in zip(*parts, strict=False):
        if len(set(components)) != 1:
            break
        common.append(components[0])
    return PurePosixPath(*common).as_posix()


def _consumer_label(usage: UsageRecord) -> str:
    label: str = format_identity(identity=usage.consumer)
    if usage.through is not None:
        label += f" through {format_identity(identity=usage.through)}"
    return label


def _message(
    *,
    declaration: DeclarationRecord,
    required_scope: ScopeKind,
    required_path: str | None,
    consumers: str,
) -> str:
    current_path: str = declaration.owning_path or declaration.ownership_root.path
    if required_scope is ScopeKind.GLOBAL:
        target: str = f"top-level {declaration.identity.kind.value}s/"
    else:
        prefix: str = "_" if required_scope is ScopeKind.LOCAL else ""
        target = f"{required_path}/{prefix}{declaration.identity.kind.value}s/"
    return (
        f"Declaration '{format_identity(identity=declaration.identity)}' is currently "
        f"{_scope_label(declaration.scope)} at '{current_path}' ({declaration.path}); required "
        f"{_scope_label(required_scope)} at '{required_path or 'top-level root'}'. Consumers: "
        f"{consumers}. Move it to '{target}'"
    )


def _scope_label(scope: ScopeKind) -> str:
    return {
        ScopeKind.GLOBAL: "project",
        ScopeKind.INHERITED: "descendant-public",
        ScopeKind.LOCAL: "exact-owner-private",
        ScopeKind.PRIVATE: "model-private",
    }[scope]


def _diagnostic(
    *, declaration: DeclarationRecord, code: ScopeDiagnosticCode, message: str
) -> ScopeDiagnostic:
    return ScopeDiagnostic(
        code=code,
        message=message,
        path=declaration.path,
        line=declaration.line,
        column=declaration.column,
        declaration=declaration.identity,
    )


def _diagnostic_key(item: ScopeDiagnostic) -> tuple[str, int, int, str, str]:
    return (item.path or "", item.line or 0, item.column or 0, item.code.value, item.message)
