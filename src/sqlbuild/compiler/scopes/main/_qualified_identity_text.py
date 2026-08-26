"""Format one qualified scope identity."""

from __future__ import annotations

from sqlbuild.compiler.scopes._helpers.identities import format_identity
from sqlbuild.compiler.scopes.models import DeclarationIdentity, ResourceIdentity


def format_qualified_identity(*, identity: ResourceIdentity | DeclarationIdentity) -> str:
    """Format a resource, public declaration, or owner-qualified private declaration."""

    return format_identity(identity=identity)
