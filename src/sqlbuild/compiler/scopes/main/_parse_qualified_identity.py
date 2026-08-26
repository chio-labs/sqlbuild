"""Parse one qualified scope identity."""

from __future__ import annotations

from sqlbuild.compiler.scopes._helpers.identities import parse_identity
from sqlbuild.compiler.scopes.models import DeclarationIdentity, ResourceIdentity


def parse_qualified_identity(*, value: str) -> ResourceIdentity | DeclarationIdentity:
    """Parse only explicit kind-qualified identities; bare names are invalid."""

    return parse_identity(value=value)
