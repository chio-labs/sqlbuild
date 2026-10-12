"""Public declaration relocation for a resource move."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.scopes.models import DeclarationRecord, ResourceIdentity, ScopeIndex


def relocate_declarations_for_move(
    *, index: ScopeIndex, resource: ResourceIdentity, destination: str
) -> tuple[DeclarationRecord, ...] | None:
    """Return declarations that must move, at their new paths, when a resource moves."""

    return _native.scope_relocated_declarations(index, resource, destination)
