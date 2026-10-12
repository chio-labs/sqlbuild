"""Public recursive declaration folder list operation."""

from pathlib import PurePath

import sqlbuild._native as _native
from sqlbuild.compiler.scopes.models import (
    ResourceIdentity,
    ScopeListResult,
    ScopeLookup,
    ScopeReportFilters,
)


def list_scope_declarations(
    *,
    lookup: ScopeLookup,
    folder: str,
    filters: ScopeReportFilters | None = None,
    target: str | PurePath | ResourceIdentity | None = None,
    target_is_prospective: bool = False,
) -> ScopeListResult:
    """List declarations recursively beneath one browsed folder."""

    return _native.scope_list(lookup, (folder, filters, target, target_is_prospective))
