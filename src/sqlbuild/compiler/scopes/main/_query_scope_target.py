"""Resources a scope query names, by identity or authored path."""

from __future__ import annotations

from pathlib import PurePath

from sqlbuild.compiler.scopes._helpers import visibility
from sqlbuild.compiler.scopes.models import ResourceIdentity, ScopeLookup, ScopeTargetQuery


def query_scope_target(
    *, lookup: ScopeLookup, target: ResourceIdentity | str | PurePath
) -> ScopeTargetQuery:
    """Return the resources or declarations `target` names."""

    return visibility.query_target(lookup=lookup, target=target)
