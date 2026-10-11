"""Visibility of one declaration from an authored consumer path, checked natively."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.scopes._helpers.visibility import declaration_lexical_path
from sqlbuild.compiler.scopes.exceptions import InvalidScopePathError
from sqlbuild.compiler.scopes.models import DeclarationRecord, ResourceIdentity


def declaration_visible(
    *, declaration: DeclarationRecord, consumer: str | DeclarationRecord
) -> bool:
    """Return whether a declaration is visible from a resource path or a declaration's folder."""

    path: str = (
        declaration_lexical_path(record=consumer)
        if isinstance(consumer, DeclarationRecord)
        else consumer
    )
    owner: ResourceIdentity | None = declaration.identity.owner
    visible: bool | None
    message: str | None
    visible, message = _native.scope_path_visible(
        declaration.scope.value,
        None if owner is None else (owner.kind.value, owner.name),
        declaration.owning_path,
        path,
    )
    if visible is None:
        raise InvalidScopePathError(message or "")
    return visible
