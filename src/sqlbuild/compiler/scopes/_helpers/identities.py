"""Pure qualified scope identity implementation."""

from __future__ import annotations

from sqlbuild.compiler.scopes.constants import (
    PRIVATE_IDENTITY_PART_COUNT,
    PUBLIC_IDENTITY_PART_COUNT,
)
from sqlbuild.compiler.scopes.exceptions import InvalidQualifiedIdentityError
from sqlbuild.compiler.scopes.models import DeclarationIdentity, ResourceIdentity
from sqlbuild.compiler.scopes.types import DeclarationKind, ResourceKind


def format_identity(*, identity: ResourceIdentity | DeclarationIdentity) -> str:
    if isinstance(identity, ResourceIdentity):
        return f"{identity.kind.value}:{identity.name}"
    if identity.owner is None:
        return f"{identity.kind.value}:{identity.name}"
    return (
        f"{identity.kind.value}:{identity.owner.kind.value}:{identity.owner.name}.{identity.name}"
    )


def parse_identity(*, value: str) -> ResourceIdentity | DeclarationIdentity:
    parts: list[str] = value.split(":")
    if len(parts) == PUBLIC_IDENTITY_PART_COUNT:
        raw_kind, name = parts
        if not name:
            raise InvalidQualifiedIdentityError(f"Qualified identity has no name: {value!r}")
        try:
            return ResourceIdentity(kind=ResourceKind(raw_kind), name=name)
        except ValueError:
            try:
                return DeclarationIdentity(kind=DeclarationKind(raw_kind), name=name)
            except ValueError as error:
                raise InvalidQualifiedIdentityError(
                    f"Unknown qualified identity kind: {raw_kind!r}"
                ) from error
    if len(parts) == PRIVATE_IDENTITY_PART_COUNT:
        raw_kind, raw_owner_kind, owner_and_name = parts
        try:
            kind: DeclarationKind = DeclarationKind(raw_kind)
            owner_kind: ResourceKind = ResourceKind(raw_owner_kind)
        except ValueError as error:
            raise InvalidQualifiedIdentityError(f"Invalid private identity: {value!r}") from error
        owner_name, separator, name = owner_and_name.rpartition(".")
        if not separator or not owner_name or not name:
            raise InvalidQualifiedIdentityError(f"Invalid private identity: {value!r}")
        return DeclarationIdentity(
            kind=kind,
            name=name,
            owner=ResourceIdentity(kind=owner_kind, name=owner_name),
        )
    raise InvalidQualifiedIdentityError(
        f"Expected a kind-qualified identity such as 'model:name': {value!r}"
    )
