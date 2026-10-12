"""Build immutable lookup indexes over canonical scope facts."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.scopes.models import ScopeIndex, ScopeLookup


def build_scope_lookup(*, index: ScopeIndex) -> ScopeLookup:
    """Canonicalize scope facts and build deeply immutable lookup mappings."""

    return _native.build_scope_lookup(index)
