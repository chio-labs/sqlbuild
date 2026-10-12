"""Resolve static declaration visibility without per-declaration inaccessible reasons."""

from __future__ import annotations

from pathlib import PurePath

import sqlbuild._native as _native
from sqlbuild.compiler.scopes.models import DeclarationVisibility, ResourceIdentity, ScopeLookup


def resolve_scope_declaration_visibility(
    *, lookup: ScopeLookup, target: ResourceIdentity | str | PurePath
) -> DeclarationVisibility:
    """Return visible facts and inaccessible declaration identities for one target."""

    return _native.scope_resolve_visibility(lookup, target, False)
