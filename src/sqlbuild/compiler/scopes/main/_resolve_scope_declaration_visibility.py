"""Resolve static declaration visibility without per-declaration inaccessible reasons."""

from __future__ import annotations

from pathlib import PurePath

from sqlbuild.compiler.scopes._helpers.visibility import resolve_declaration_visibility
from sqlbuild.compiler.scopes.models import DeclarationVisibility, ResourceIdentity, ScopeLookup


def resolve_scope_declaration_visibility(
    *, lookup: ScopeLookup, target: ResourceIdentity | str | PurePath
) -> DeclarationVisibility:
    """Return visible facts and inaccessible declaration identities for one target."""

    return resolve_declaration_visibility(lookup=lookup, target=target)
