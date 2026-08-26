"""Query a scope resource by qualified identity or normalized authored path."""

from __future__ import annotations

from pathlib import PurePath

from sqlbuild.compiler.scopes._helpers.visibility import query_target
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    ResourceIdentity,
    ScopeLookup,
    ScopeTargetQuery,
)


def query_scope_target(
    *,
    lookup: ScopeLookup,
    target: ResourceIdentity | DeclarationIdentity | str | PurePath,
) -> ScopeTargetQuery:
    """Return matching resource or declaration records without conflating absence."""

    return query_target(lookup=lookup, target=target)
