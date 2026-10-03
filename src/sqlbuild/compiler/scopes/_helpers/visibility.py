"""Canonical record-level declaration visibility resolution."""

from __future__ import annotations

from functools import lru_cache
from pathlib import PurePath
from types import MappingProxyType

from sqlbuild.compiler.scopes._helpers.identities import parse_identity
from sqlbuild.compiler.scopes._helpers.paths import normalize_path
from sqlbuild.compiler.scopes.constants import (
    CURRENT_PATH_COMPONENT,
    PATH_SEPARATOR,
    QUALIFIED_IDENTITY_SEPARATOR,
)
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationRecord,
    DeclarationVisibility,
    DeclarationVisibilityIndex,
    GrantRecord,
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
    GrantKind,
    InaccessibleReason,
    OwnershipRootKind,
    ResourceKind,
    ScopeKind,
    VisibilityReason,
)

_DECLARATION_STEM: str = "__declaration__.sql"


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
    query, visible, inaccessible_groups = _classify_target(lookup=lookup, target=target)
    declarations: tuple[DeclarationRecord, ...] = lookup.index.declarations
    inaccessible: list[InaccessibleRecord] = []
    resource: ResourceRecord
    positions: list[int]
    for resource, positions in inaccessible_groups:
        inaccessible.extend(
            InaccessibleRecord(
                resource.identity,
                declarations[position].identity,
                _inaccessible_reason(resource=resource, declaration=declarations[position]),
            )
            for position in positions
        )
    return VisibilityResolution(query, tuple(visible), tuple(inaccessible))


def resolve_declaration_visibility(
    *, lookup: ScopeLookup, target: ResourceIdentity | str | PurePath
) -> DeclarationVisibility:
    """Resolve visible facts and inaccessible identities without per-pair inaccessible reasons."""

    query, visible, inaccessible_groups = _classify_target(lookup=lookup, target=target)
    identities: tuple[DeclarationIdentity, ...] = lookup.visibility_index.identities
    inaccessible: list[DeclarationIdentity] = []
    positions: list[int]
    for _resource, positions in inaccessible_groups:
        inaccessible.extend(identities[position] for position in positions)
    return DeclarationVisibility(query, tuple(visible), tuple(inaccessible))


def _classify_target(
    *, lookup: ScopeLookup, target: ResourceIdentity | str | PurePath
) -> tuple[ScopeTargetQuery, list[VisibilityRecord], list[tuple[ResourceRecord, list[int]]]]:
    """Return the query, ordered visible records, and inaccessible positions per match."""

    query: ScopeTargetQuery = query_target(lookup=lookup, target=target)
    visible: list[VisibilityRecord] = []
    inaccessible_groups: list[tuple[ResourceRecord, list[int]]] = []
    resource: ResourceRecord
    for resource in query.matches:
        resource_visible, positions = _classify_resource(lookup=lookup, resource=resource)
        visible.extend(resource_visible)
        inaccessible_groups.append((resource, positions))
    return query, visible, inaccessible_groups


def _classify_resource(
    *, lookup: ScopeLookup, resource: ResourceRecord
) -> tuple[list[VisibilityRecord], list[int]]:
    """Return ordered visible records and the declaration positions left inaccessible."""

    index: DeclarationVisibilityIndex = lookup.visibility_index
    positive: list[tuple[int, VisibilityReason]] = _visible_positions(
        index=index, resource=resource
    )
    grants: tuple[GrantRecord, ...] = lookup.grants_by_resource.get(resource.identity, ())
    if not grants:
        visible_positions: set[int] = {position for position, _reason in positive}
        return (
            [
                VisibilityRecord(resource.identity, index.identities[position], reason)
                for position, reason in positive
            ],
            [
                position
                for position in range(len(index.identities))
                if position not in visible_positions
            ],
        )
    reasons: dict[int, VisibilityReason] = dict(positive)
    grants_by_declaration: dict[DeclarationIdentity, list[GrantRecord]] = {}
    for grant in grants:
        grants_by_declaration.setdefault(grant.declaration, []).append(grant)
    visible: list[VisibilityRecord] = []
    inaccessible: list[int] = []
    position: int
    identity: DeclarationIdentity
    for position, identity in enumerate(index.identities):
        reason: VisibilityReason | None = reasons.get(position)
        if reason is not None:
            visible.append(VisibilityRecord(resource.identity, identity, reason))
        declaration_grants: list[GrantRecord] | None = grants_by_declaration.get(identity)
        if declaration_grants is not None:
            visible.extend(
                VisibilityRecord(
                    resource.identity,
                    identity,
                    (
                        VisibilityReason.TESTED_MACRO
                        if grant.kind is GrantKind.TESTED_MACRO
                        else VisibilityReason.EXPECTED_MODEL
                    ),
                    grant.through,
                )
                for grant in declaration_grants
            )
        elif reason is None:
            inaccessible.append(position)
    return visible, inaccessible


def build_visibility_index(
    *, declarations: tuple[DeclarationRecord, ...]
) -> DeclarationVisibilityIndex:
    """Group canonical declaration positions by the scope facts that make them visible."""

    global_positions: list[int] = []
    private: dict[ResourceIdentity, list[int]] = {}
    local: dict[str, list[int]] = {}
    inherited: dict[str, list[int]] = {}
    position: int
    declaration: DeclarationRecord
    for position, declaration in enumerate(declarations):
        if declaration.scope is ScopeKind.GLOBAL:
            global_positions.append(position)
        elif declaration.scope is ScopeKind.PRIVATE and declaration.identity.owner is not None:
            private.setdefault(declaration.identity.owner, []).append(position)
        elif declaration.scope is ScopeKind.LOCAL:
            local.setdefault(_declaration_owner(declaration), []).append(position)
        elif declaration.scope is ScopeKind.INHERITED:
            inherited.setdefault(_declaration_owner(declaration), []).append(position)
    return DeclarationVisibilityIndex(
        identities=tuple(declaration.identity for declaration in declarations),
        global_positions=tuple(global_positions),
        private_positions=MappingProxyType(
            {owner: tuple(positions) for owner, positions in private.items()}
        ),
        local_positions=MappingProxyType(
            {owner: tuple(positions) for owner, positions in local.items()}
        ),
        inherited_positions=MappingProxyType(
            {owner: tuple(positions) for owner, positions in inherited.items()}
        ),
    )


def _visible_positions(
    *, index: DeclarationVisibilityIndex, resource: ResourceRecord
) -> list[tuple[int, VisibilityReason]]:
    """Return declaration positions visible to a resource, in declaration order."""

    positive: list[tuple[int, VisibilityReason]] = [
        (position, VisibilityReason.GLOBAL) for position in index.global_positions
    ]
    positive.extend(
        (position, VisibilityReason.PRIVATE_OWNER)
        for position in index.private_positions.get(resource.identity, ())
    )
    if index.local_positions or index.inherited_positions:
        parent: str = _parent(resource.path)
        positive.extend(
            (position, VisibilityReason.LOCAL_OWNER)
            for position in index.local_positions.get(parent, ())
        )
        ancestor: str
        for ancestor in _canonical_ancestors(parent):
            positive.extend(
                (position, VisibilityReason.INHERITED_ANCESTOR)
                for position in index.inherited_positions.get(ancestor, ())
            )
    positive.sort()
    return positive


def _declaration_owner(declaration: DeclarationRecord) -> str:
    return _canonical_owner(declaration.owning_path or CURRENT_PATH_COMPONENT)


@lru_cache(maxsize=65_536)
def _canonical_ancestors(path: str) -> tuple[str, ...]:
    """Return every owner that ``_is_canonical_descendant`` accepts as an ancestor of ``path``."""

    prefixes: list[str] = [CURRENT_PATH_COMPONENT]
    index: int = path.find(PATH_SEPARATOR)
    while index >= 0:
        prefixes.append(path[:index])
        index = path.find(PATH_SEPARATOR, index + 1)
    prefixes.append(path)
    return tuple(dict.fromkeys(prefixes))


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


def declaration_lexical_path(*, record: DeclarationRecord) -> str:
    """Return the authored path whose folder controls what a declaration file can use."""

    return f"{record.owning_path or CURRENT_PATH_COMPONENT}{PATH_SEPARATOR}{_DECLARATION_STEM}"


def path_visibility_reason(
    *, declaration: DeclarationRecord, path: str | PurePath
) -> VisibilityReason | None:
    """Return why a public declaration is visible from an authored path, if it is."""

    normalized_path: str = normalize_path(path=path)
    return _visibility_reason(
        resource=ResourceRecord(
            identity=ResourceIdentity(ResourceKind.MODEL, f"<path:{normalized_path}>"),
            path=normalized_path,
            ownership_root=OwnershipRoot(path=CURRENT_PATH_COMPONENT),
        ),
        declaration=declaration,
    )


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
    owner: str = _canonical_owner(declaration.owning_path or CURRENT_PATH_COMPONENT)
    parent: str = _parent(resource.path)
    if declaration.scope is ScopeKind.LOCAL:
        return VisibilityReason.LOCAL_OWNER if parent == owner else None
    if declaration.scope is ScopeKind.INHERITED and _is_canonical_descendant(
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
    owner: str = _canonical_owner(declaration.owning_path or CURRENT_PATH_COMPONENT)
    parent: str = _parent(resource.path)
    if _is_canonical_descendant(path=owner, ancestor=parent):
        return InaccessibleReason.DESCENDANT_SCOPE
    if declaration.ownership_root.path == resource.ownership_root.path:
        return InaccessibleReason.SIBLING_SCOPE
    return InaccessibleReason.UNRELATED_SCOPE


@lru_cache(maxsize=65_536)
def _parent(path: str) -> str:
    normalized: str = normalize_path(path=path)
    return (
        normalized.rsplit(PATH_SEPARATOR, maxsplit=1)[0]
        if PATH_SEPARATOR in normalized
        else CURRENT_PATH_COMPONENT
    )


def _is_canonical_descendant(*, path: str, ancestor: str) -> bool:
    return (
        ancestor == CURRENT_PATH_COMPONENT
        or path == ancestor
        or path.startswith(f"{ancestor}{PATH_SEPARATOR}")
    )


@lru_cache(maxsize=65_536)
def _canonical_owner(path: str) -> str:
    return normalize_path(path=path)
