"""Declaration visibility over a scope lookup, resolved by the native scope lookup."""

from __future__ import annotations

from pathlib import PurePath
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.scopes._helpers.paths import normalize_path
from sqlbuild.compiler.scopes._helpers.placement import qualified_row, root_row
from sqlbuild.compiler.scopes.constants import CURRENT_PATH_COMPONENT, PATH_SEPARATOR
from sqlbuild.compiler.scopes.exceptions import InvalidQualifiedIdentityError, InvalidScopePathError
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationRecord,
    DeclarationVisibility,
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
    NativeResolvedRows,
    NativeResourceRecordRow,
    OwnershipRootKind,
    ResourceKind,
    VisibilityReason,
)

_DECLARATION_STEM: str = "__declaration__.sql"


def query_target(
    *, lookup: ScopeLookup, target: ResourceIdentity | DeclarationIdentity | str | PurePath
) -> ScopeTargetQuery:
    """The resources or declarations `target` names; invalid text raises the scope error."""

    identity: bool = isinstance(target, (ResourceIdentity, DeclarationIdentity))
    raw: str = "" if identity else str(target)
    declarations, positions, identity_error, path_error = _lookup(lookup).target(
        qualified_row(identity=cast("ResourceIdentity | DeclarationIdentity", target))
        if identity
        else None,
        raw,
    )
    if identity_error is not None:
        raise InvalidQualifiedIdentityError(identity_error)
    if path_error is not None:
        raise InvalidScopePathError(path_error)
    value: str | ResourceIdentity | DeclarationIdentity = (
        cast("ResourceIdentity | DeclarationIdentity", target) if identity else raw
    )
    if declarations:
        return ScopeTargetQuery(
            value,
            declaration_matches=tuple(lookup.index.declarations[item] for item in positions),
        )
    return ScopeTargetQuery(value, tuple(lookup.index.resources[item] for item in positions))


def resolve_visibility(
    *, lookup: ScopeLookup, target: ResourceIdentity | str | PurePath
) -> VisibilityResolution:
    """Every visible fact and inaccessible declaration, with reasons, of each matched resource."""

    query: ScopeTargetQuery = query_target(lookup=lookup, target=target)
    visible: list[VisibilityRecord] = []
    inaccessible: list[InaccessibleRecord] = []
    for resource in query.matches:
        resource_visible, resource_inaccessible = _resolve(lookup=lookup, resource=resource)
        visible.extend(resource_visible)
        inaccessible.extend(
            InaccessibleRecord(
                resource.identity,
                lookup.index.declarations[position].identity,
                InaccessibleReason(reason),
            )
            for position, reason in resource_inaccessible
        )
    return VisibilityResolution(query, tuple(visible), tuple(inaccessible))


def resolve_declaration_visibility(
    *, lookup: ScopeLookup, target: ResourceIdentity | str | PurePath
) -> DeclarationVisibility:
    """Resolve visible facts and inaccessible identities without per-pair inaccessible reasons."""

    query: ScopeTargetQuery = query_target(lookup=lookup, target=target)
    visible: list[VisibilityRecord] = []
    inaccessible: list[DeclarationIdentity] = []
    for resource in query.matches:
        resource_visible, resource_inaccessible = _resolve(lookup=lookup, resource=resource)
        visible.extend(resource_visible)
        inaccessible.extend(
            lookup.index.declarations[position].identity for position, _ in resource_inaccessible
        )
    return DeclarationVisibility(query, tuple(visible), tuple(inaccessible))


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
    visible, inaccessible, error = _resolved_rows(lookup=lookup, resource=resource)
    if error is not None:
        raise InvalidScopePathError(error)
    declarations: tuple[DeclarationRecord, ...] = lookup.index.declarations
    return (
        tuple(declarations[position] for position, _, _ in visible),
        tuple(declarations[position] for position, _ in inaccessible),
    )


def declaration_lexical_path(*, record: DeclarationRecord) -> str:
    """Return the authored path whose folder controls what a declaration file can use."""

    return f"{record.owning_path or CURRENT_PATH_COMPONENT}{PATH_SEPARATOR}{_DECLARATION_STEM}"


def _resolve(
    *, lookup: ScopeLookup, resource: ResourceRecord
) -> tuple[list[VisibilityRecord], list[tuple[int, str]]]:
    visible, inaccessible, error = _resolved_rows(lookup=lookup, resource=resource)
    if error is not None:
        raise InvalidScopePathError(error)
    identities: tuple[DeclarationIdentity, ...] = lookup.visibility_index.identities
    return (
        [
            VisibilityRecord(
                resource.identity,
                identities[position],
                VisibilityReason(reason),
                None if grant is None else lookup.index.grants[grant].through,
            )
            for position, reason, grant in visible
        ],
        inaccessible,
    )


def _resolved_rows(*, lookup: ScopeLookup, resource: ResourceRecord) -> NativeResolvedRows:
    return _lookup(lookup).resolve(_resource_row(resource=resource))


def _resource_row(*, resource: ResourceRecord) -> NativeResourceRecordRow:
    return (
        (resource.identity.kind.value, resource.identity.name),
        resource.path,
        root_row(root=resource.ownership_root),
    )


def _lookup(lookup: ScopeLookup) -> _native.NativeScopeLookup:
    return cast(_native.NativeScopeLookup, lookup.native)
