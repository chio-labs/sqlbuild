"""Scope identities and ownership roots as the rows the native scope engine reads."""

from __future__ import annotations

from sqlbuild.compiler.scopes.models import DeclarationIdentity, OwnershipRoot, ResourceIdentity
from sqlbuild.compiler.scopes.types import NativeQualifiedRow, NativeRootRow


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
