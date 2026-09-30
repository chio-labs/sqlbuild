"""Public declaration relocation for a resource move."""

from __future__ import annotations

from sqlbuild.compiler.scopes._helpers.placement import relocate_for_resource_move
from sqlbuild.compiler.scopes.models import DeclarationRecord, ResourceIdentity, ScopeIndex


def relocate_declarations_for_move(
    *, index: ScopeIndex, resource: ResourceIdentity, destination: str
) -> tuple[DeclarationRecord, ...] | None:
    """Return declarations that must move, at their new paths, when a resource moves."""

    return relocate_for_resource_move(index=index, resource=resource, destination=destination)
