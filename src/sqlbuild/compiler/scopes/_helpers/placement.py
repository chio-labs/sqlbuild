"""Validate declaration usage and exact lexical placement."""

from __future__ import annotations

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
    usages: dict[DeclarationIdentity, list[UsageRecord]] = {}
    for usage in index.usages:
        usages.setdefault(usage.declaration, []).append(usage)

    diagnostics: list[ScopeDiagnostic] = [
        item for item in index.diagnostics if item.code not in _PLACEMENT_CODES
    ]
    for declaration in index.declarations:
        declaration_usages: list[UsageRecord] = usages.get(declaration.identity, [])
        if declaration.scope is ScopeKind.PRIVATE:
            declaration_usages = [
                usage
                for usage in declaration_usages
                if usage.consumer == declaration.identity.owner and usage.through is None
            ]
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
        required: tuple[ScopeKind, str | None, tuple[str, ...]] | None = resolve_required_placement(
            index=index, declaration=declaration.identity
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
    record: DeclarationRecord = records[0]
    if record.scope is ScopeKind.PRIVATE:
        direct_private: tuple[UsageRecord, ...] = tuple(
            usage
            for usage in index.usages
            if usage.declaration == declaration
            and usage.consumer == declaration.owner
            and usage.through is None
        )
        return (
            (ScopeKind.PRIVATE, record.owning_path or record.ownership_root.path, ())
            if direct_private
            else None
        )
    declaration_usages: tuple[UsageRecord, ...] = tuple(
        usage for usage in index.usages if usage.declaration == declaration
    )
    if not declaration_usages:
        return None
    resources: dict[ResourceIdentity, ResourceRecord] = {
        item.identity: item for item in index.resources
    }
    usage_lists: dict[DeclarationIdentity, list[UsageRecord]] = {}
    for usage in index.usages:
        usage_lists.setdefault(usage.declaration, []).append(usage)
    usages_by_declaration: dict[DeclarationIdentity, tuple[UsageRecord, ...]] = {
        identity: tuple(usages) for identity, usages in usage_lists.items()
    }
    anchor_list: list[tuple[OwnershipRoot, str]] = []
    for usage in declaration_usages:
        anchor_list.extend(
            _usage_anchors(
                usage=usage,
                resources=resources,
                usages_by_declaration=usages_by_declaration,
                visited=frozenset({declaration}),
            )
        )
    anchors: tuple[tuple[OwnershipRoot, str], ...] = tuple(anchor_list)
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


def _usage_anchors(
    *,
    usage: UsageRecord,
    resources: dict[ResourceIdentity, ResourceRecord],
    usages_by_declaration: dict[DeclarationIdentity, tuple[UsageRecord, ...]],
    visited: frozenset[DeclarationIdentity],
) -> tuple[tuple[OwnershipRoot, str], ...]:
    resource_identity: ResourceIdentity | None = usage.through
    if resource_identity is None and isinstance(usage.consumer, ResourceIdentity):
        resource_identity = usage.consumer
    if resource_identity is not None:
        resource: ResourceRecord | None = resources.get(resource_identity)
        if resource is None:
            return ()
        return ((resource.ownership_root, PurePosixPath(resource.path).parent.as_posix()),)
    if not isinstance(usage.consumer, DeclarationIdentity):
        return ()
    if usage.consumer in visited:
        return ()
    anchors: list[tuple[OwnershipRoot, str]] = []
    for parent_usage in usages_by_declaration.get(usage.consumer, ()):
        anchors.extend(
            _usage_anchors(
                usage=parent_usage,
                resources=resources,
                usages_by_declaration=usages_by_declaration,
                visited=visited | {usage.consumer},
            )
        )
    return tuple(anchors)


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
