"""Resolve canonical static declaration visibility for one target."""

from __future__ import annotations

from pathlib import PurePath

from sqlbuild.compiler.scopes._helpers.visibility import resolve_visibility
from sqlbuild.compiler.scopes.models import ResourceIdentity, ScopeLookup, VisibilityResolution


def resolve_scope_visibility(
    *, lookup: ScopeLookup, target: ResourceIdentity | str | PurePath
) -> VisibilityResolution:
    """Return visible and inaccessible facts, or an explicit unknown target result."""

    return resolve_visibility(lookup=lookup, target=target)
