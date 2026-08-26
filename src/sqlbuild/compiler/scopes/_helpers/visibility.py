"""Canonical record-level declaration visibility resolution."""

from __future__ import annotations

from pathlib import PurePath

from sqlbuild.compiler.scopes._helpers.identities import parse_identity
from sqlbuild.compiler.scopes._helpers.paths import is_equal_or_descendant, normalize_path
from sqlbuild.compiler.scopes.constants import (
    CURRENT_PATH_COMPONENT,
    PATH_SEPARATOR,
    QUALIFIED_IDENTITY_SEPARATOR,
)
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationRecord,
    InaccessibleRecord,
    OwnershipRoot,
    ResourceIdentity,
    ResourceRecord,
    ScopeLookup,
    ScopeTargetQuery,
    VisibilityRecord,
    VisibilityResolution,
)
from sqlbuild.compiler.scopes.types import (
    InaccessibleReason,
    OwnershipRootKind,
    ResourceKind,
    ScopeKind,
    VisibilityReason,
)


def query_target(
    *, lookup: ScopeLookup, target: ResourceIdentity | DeclarationIdentity | str | PurePath
) -> ScopeTargetQuery:
    if isinstance(target, ResourceIdentity):
        return ScopeTargetQuery(target, lookup.resources.get(target, ()))
    if isinstance(target, DeclarationIdentity):
        return ScopeTargetQuery(
            target,
            declaration_matches=lookup.declarations.get(target, ()),
        )
    raw: str = str(target)
    if QUALIFIED_IDENTITY_SEPARATOR in raw:
        identity: ResourceIdentity | DeclarationIdentity = parse_identity(value=raw)
        if isinstance(identity, ResourceIdentity):
            return ScopeTargetQuery(raw, lookup.resources.get(identity, ()))
        return ScopeTargetQuery(
            raw,
            declaration_matches=lookup.declarations.get(identity, ()),
        )
    return ScopeTargetQuery(raw, lookup.resources_by_path.get(normalize_path(path=raw), ()))


def resolve_visibility(
    *, lookup: ScopeLookup, target: ResourceIdentity | str | PurePath
) -> VisibilityResolution:
    query: ScopeTargetQuery = query_target(lookup=lookup, target=target)
    if query.unknown:
        return VisibilityResolution(target=query)
    visible: list[VisibilityRecord] = []
    inaccessible: list[InaccessibleRecord] = []
    resource: ResourceRecord
    for resource in query.matches:
        declaration: DeclarationRecord
        for declaration in lookup.index.declarations:
            positive: VisibilityReason | None = _visibility_reason(
                resource=resource, declaration=declaration
            )
            if positive is not None:
                visible.append(VisibilityRecord(resource.identity, declaration.identity, positive))
            else:
                inaccessible.append(
                    InaccessibleRecord(
                        resource.identity,
                        declaration.identity,
                        _inaccessible_reason(resource=resource, declaration=declaration),
                    )
                )
    return VisibilityResolution(query, tuple(visible), tuple(inaccessible))


def resolve_path_visibility(
    *, lookup: ScopeLookup, path: str | PurePath
) -> tuple[tuple[DeclarationRecord, ...], tuple[DeclarationRecord, ...]]:
    """Classify declarations for an authored path, including declaration definition files."""

    normalized_path: str = normalize_path(path=path)
    resource: ResourceRecord = ResourceRecord(
        identity=ResourceIdentity(ResourceKind.MODEL, f"<path:{normalized_path}>"),
        path=normalized_path,
        ownership_root=OwnershipRoot(
            path=CURRENT_PATH_COMPONENT,
            kind=OwnershipRootKind.RESOURCE,
            resource_kind=ResourceKind.MODEL,
        ),
    )
    visible: list[DeclarationRecord] = []
    inaccessible: list[DeclarationRecord] = []
    for declaration in lookup.index.declarations:
        target: list[DeclarationRecord] = (
            visible
            if _visibility_reason(resource=resource, declaration=declaration) is not None
            else inaccessible
        )
        target.append(declaration)
    return tuple(visible), tuple(inaccessible)


def _visibility_reason(
    *, resource: ResourceRecord, declaration: DeclarationRecord
) -> VisibilityReason | None:
    if declaration.scope is ScopeKind.GLOBAL:
        return VisibilityReason.GLOBAL
    if declaration.scope is ScopeKind.PRIVATE:
        return (
            VisibilityReason.PRIVATE_OWNER
            if declaration.identity.owner == resource.identity
            else None
        )
    owner: str = declaration.owning_path or CURRENT_PATH_COMPONENT
    parent: str = _parent(resource.path)
    if declaration.scope is ScopeKind.LOCAL:
        return VisibilityReason.LOCAL_OWNER if parent == owner else None
    if declaration.scope is ScopeKind.INHERITED and is_equal_or_descendant(
        path=parent, ancestor=owner
    ):
        return VisibilityReason.INHERITED_ANCESTOR
    return None


def _inaccessible_reason(
    *, resource: ResourceRecord, declaration: DeclarationRecord
) -> InaccessibleReason:
    if declaration.scope is ScopeKind.PRIVATE:
        return InaccessibleReason.PRIVATE_OWNER
    if declaration.scope is ScopeKind.LOCAL:
        return InaccessibleReason.LOCAL_BOUNDARY
    owner: str = declaration.owning_path or CURRENT_PATH_COMPONENT
    parent: str = _parent(resource.path)
    if is_equal_or_descendant(path=owner, ancestor=parent):
        return InaccessibleReason.DESCENDANT_SCOPE
    if declaration.ownership_root.path == resource.ownership_root.path:
        return InaccessibleReason.SIBLING_SCOPE
    return InaccessibleReason.UNRELATED_SCOPE


def _parent(path: str) -> str:
    normalized: str = normalize_path(path=path)
    return (
        normalized.rsplit(PATH_SEPARATOR, maxsplit=1)[0]
        if PATH_SEPARATOR in normalized
        else CURRENT_PATH_COMPONENT
    )
