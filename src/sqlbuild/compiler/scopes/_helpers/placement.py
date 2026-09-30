"""Validate declaration usage and exact lexical placement."""

from __future__ import annotations

from collections import deque
from dataclasses import replace
from pathlib import PurePosixPath

from sqlbuild.compiler.discovery.constants import CANONICAL_AUTHORED_ROOTS
from sqlbuild.compiler.scopes._helpers.identities import format_identity
from sqlbuild.compiler.scopes.constants import (
    DECLARATION_GROUP_DIRECTORY,
    DECLARATION_ROLE_PARTS,
    NAMED_DECLARATION_KINDS,
)
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
from sqlbuild.compiler.scopes.types import (
    DeclarationKind,
    DiagnosticSeverity,
    OwnershipRootKind,
    ScopeDiagnosticCode,
    ScopeKind,
)

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
_PROJECT_ROOT_PATH: str = "."
_AUTHORED_ROOT_PATHS: frozenset[str] = frozenset(
    PurePosixPath(*parts).as_posix() for parts in CANONICAL_AUTHORED_ROOTS
)


def build_placement_validated_index(
    *, index: ScopeIndex, enforce_placement: bool = True
) -> ScopeIndex:
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
            if declaration.identity.kind is DeclarationKind.SINGULAR_AUDIT:
                continue
            diagnostics.append(
                _diagnostic(
                    declaration=declaration,
                    code=ScopeDiagnosticCode.UNUSED_DECLARATION,
                    enforce_placement=enforce_placement,
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
                    enforce_placement=enforce_placement,
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
                enforce_placement=enforce_placement,
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


def declaration_directory(*, kind: DeclarationKind, scope: ScopeKind, path: str | None) -> str:
    """Return the project-relative folder where a declaration with this placement lives."""

    role_parts: tuple[str, ...] = DECLARATION_ROLE_PARTS[kind]
    if scope is ScopeKind.GLOBAL or path is None:
        return "/".join(role_parts)
    prefix: str = "_" if scope is ScopeKind.LOCAL else ""
    role: str = "/".join((f"{prefix}{role_parts[0]}", *role_parts[1:]))
    if path in _AUTHORED_ROOT_PATHS:
        return f"{path}/{role}"
    return f"{path}/{DECLARATION_GROUP_DIRECTORY}/{role}"


def relocate_for_resource_move(
    *, index: ScopeIndex, resource: ResourceIdentity, destination: str
) -> tuple[DeclarationRecord, ...] | None:
    """Return declarations whose placement changes when a resource moves, or None if unsettled."""

    if not index.completeness.runtime_usage:
        return None
    misplaced: frozenset[DeclarationIdentity] = frozenset(
        item.declaration
        for item in build_placement_validated_index(index=index).diagnostics
        if item.code in _PLACEMENT_CODES and item.declaration is not None
    )
    current: ScopeIndex = replace(
        index,
        resources=tuple(
            replace(item, path=destination) if item.identity == resource else item
            for item in index.resources
        ),
    )
    usages_by_declaration: _UsagesByDeclaration = _usages_by_declaration(index=current)
    for _ in range(len(index.declarations) + 1):
        anchor_sets: _AnchorSets = _anchor_sets(
            index=current, usages_by_declaration=usages_by_declaration
        )
        relocated: dict[DeclarationIdentity, DeclarationRecord] = {}
        record: DeclarationRecord
        for record in current.declarations:
            if record.scope is ScopeKind.PRIVATE or record.identity in misplaced:
                continue
            moved: DeclarationRecord | None = _relocated_record(
                record=record,
                usages_by_declaration=usages_by_declaration,
                anchor_sets=anchor_sets,
            )
            if moved is not None:
                relocated[record.identity] = moved
        if not relocated:
            original: dict[DeclarationIdentity, DeclarationRecord] = {
                item.identity: item for item in index.declarations
            }
            return tuple(
                item for item in current.declarations if item.path != original[item.identity].path
            )
        current = replace(
            current,
            declarations=tuple(relocated.get(item.identity, item) for item in current.declarations),
        )
    return None


def _relocated_record(
    *,
    record: DeclarationRecord,
    usages_by_declaration: _UsagesByDeclaration,
    anchor_sets: _AnchorSets,
) -> DeclarationRecord | None:
    required: tuple[ScopeKind, str | None, tuple[str, ...]] | None = _required_placement_for_record(
        record=record, usages_by_declaration=usages_by_declaration, anchor_sets=anchor_sets
    )
    if required is None:
        return None
    scope: ScopeKind = required[0]
    path: str | None = required[1]
    if record.scope is scope and record.owning_path == path:
        return None
    directory: str = declaration_directory(kind=record.identity.kind, scope=scope, path=path)
    roots: set[OwnershipRoot] = {
        root for root, _path in anchor_sets.get(record.identity, frozenset())
    }
    ownership_root: OwnershipRoot = (
        OwnershipRoot(directory, OwnershipRootKind.GLOBAL)
        if scope is ScopeKind.GLOBAL or len(roots) != 1
        else next(iter(roots))
    )
    return replace(
        record,
        path=f"{directory}/{PurePosixPath(record.path).name}",
        scope=scope,
        ownership_root=ownership_root,
        owning_path=None if scope is ScopeKind.GLOBAL else path,
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
    roots: set[OwnershipRoot] = {root for root, _path in anchors}
    if len(roots) != 1 or any(root.kind is OwnershipRootKind.GLOBAL for root in roots):
        return ScopeKind.GLOBAL, None, consumers
    ownership_root: OwnershipRoot = next(iter(roots))
    paths: tuple[str, ...] = tuple(path for _root, path in anchors)
    distinct: set[str] = set(paths)
    named: bool = declaration.kind in NAMED_DECLARATION_KINDS
    if len(distinct) == 1:
        required_path: str = next(iter(distinct))
        if named and required_path == ownership_root.path:
            return ScopeKind.GLOBAL, None, consumers
        if declaration.kind is DeclarationKind.SINGULAR_AUDIT:
            return ScopeKind.INHERITED, required_path, consumers
        return ScopeKind.LOCAL, required_path, consumers
    required_path = _lca(paths)
    return (
        (ScopeKind.GLOBAL, None, consumers)
        if required_path == ownership_root.path
        else (ScopeKind.INHERITED, required_path, consumers)
    )


def _anchor_sets(*, index: ScopeIndex, usages_by_declaration: _UsagesByDeclaration) -> _AnchorSets:
    """Return each declaration's resource anchors reachable through consumer chains."""

    resources: dict[ResourceIdentity, ResourceRecord] = {
        item.identity: item for item in index.resources
    }
    declarations: dict[DeclarationIdentity, DeclarationRecord] = {
        item.identity: item for item in index.declarations
    }
    anchors: dict[DeclarationIdentity, set[_Anchor]] = {}
    dependents: dict[DeclarationIdentity, set[DeclarationIdentity]] = {}
    for identity, declaration_usages in usages_by_declaration.items():
        direct: set[_Anchor] = anchors.setdefault(identity, set())
        for usage in declaration_usages:
            if isinstance(usage.through, DeclarationIdentity):
                through_declaration: DeclarationRecord | None = declarations.get(usage.through)
                if through_declaration is not None and through_declaration.owning_path is not None:
                    direct.add(
                        (
                            through_declaration.ownership_root,
                            through_declaration.owning_path,
                        )
                    )
                continue
            if (
                usage.through is None
                and isinstance(usage.consumer, DeclarationIdentity)
                and usage.consumer.kind in NAMED_DECLARATION_KINDS
            ):
                consumer_declaration: DeclarationRecord | None = declarations.get(usage.consumer)
                if consumer_declaration is not None:
                    direct.add(_declaration_location_anchor(record=consumer_declaration))
                continue
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


def _declaration_location_anchor(*, record: DeclarationRecord) -> _Anchor:
    """Anchor a use by an audit, schema, or hook at the folder where that declaration lives."""

    if record.owning_path is None:
        return OwnershipRoot(_PROJECT_ROOT_PATH, OwnershipRootKind.GLOBAL), _PROJECT_ROOT_PATH
    return record.ownership_root, record.owning_path


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
    directory: str = declaration_directory(
        kind=declaration.identity.kind, scope=required_scope, path=required_path
    )
    target: str = (
        f"top-level {directory}/" if required_scope is ScopeKind.GLOBAL else f"{directory}/"
    )
    consumer_label: str = (
        "References" if declaration.identity.kind is DeclarationKind.SINGULAR_AUDIT else "Consumers"
    )
    return (
        f"Declaration '{format_identity(identity=declaration.identity)}' is currently "
        f"{_scope_label(declaration.scope)} at '{current_path}' ({declaration.path}); required "
        f"{_scope_label(required_scope)} at '{required_path or 'top-level root'}'. "
        f"{consumer_label}: {consumers}. Move it to '{target}'"
    )


def _scope_label(scope: ScopeKind) -> str:
    return {
        ScopeKind.GLOBAL: "project",
        ScopeKind.INHERITED: "descendant-public",
        ScopeKind.LOCAL: "exact-owner-private",
        ScopeKind.PRIVATE: "model-private",
    }[scope]


def _diagnostic(
    *,
    declaration: DeclarationRecord,
    code: ScopeDiagnosticCode,
    message: str,
    enforce_placement: bool,
) -> ScopeDiagnostic:
    return ScopeDiagnostic(
        code=code,
        message=message,
        path=declaration.path,
        line=declaration.line,
        column=declaration.column,
        declaration=declaration.identity,
        severity=(DiagnosticSeverity.ERROR if enforce_placement else DiagnosticSeverity.WARNING),
    )


def _diagnostic_key(item: ScopeDiagnostic) -> tuple[str, int, int, str, str]:
    return (item.path or "", item.line or 0, item.column or 0, item.code.value, item.message)
