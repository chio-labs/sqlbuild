"""Build immutable lookup indexes over canonical scope facts."""

from __future__ import annotations

from sqlbuild.compiler.scopes._helpers.lookup import build_lookup
from sqlbuild.compiler.scopes.models import ScopeIndex, ScopeLookup


def build_scope_lookup(*, index: ScopeIndex) -> ScopeLookup:
    """Canonicalize scope facts and build deeply immutable lookup mappings."""

    return build_lookup(index=index)
