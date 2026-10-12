"""Resolve what one scope target names."""

from __future__ import annotations

from pathlib import PurePath

import sqlbuild._native as _native
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    ResourceIdentity,
    ScopeLookup,
    ScopeTargetQuery,
)


def query_scope_target(
    *, lookup: ScopeLookup, target: ResourceIdentity | DeclarationIdentity | str | PurePath
) -> ScopeTargetQuery:
    """The resources or declarations `target` names; invalid text raises the scope error."""

    return _native.scope_query_target(lookup, target)
