"""Resolve canonical static declaration visibility for one target."""

from __future__ import annotations

from pathlib import PurePath

import sqlbuild._native as _native
from sqlbuild.compiler.scopes.models import ResourceIdentity, ScopeLookup, VisibilityResolution


def resolve_scope_visibility(
    *, lookup: ScopeLookup, target: ResourceIdentity | str | PurePath
) -> VisibilityResolution:
    """Return visible and inaccessible facts, or an explicit unknown target result."""

    return _native.scope_resolve_visibility(lookup, target, True)
