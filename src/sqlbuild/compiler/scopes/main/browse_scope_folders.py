"""Public declaration folder browse operation."""

from pathlib import PurePath

import sqlbuild._native as _native
from sqlbuild.compiler.scopes.models import ResourceIdentity, ScopeBrowseResult, ScopeLookup


def browse_scope_folders(
    *,
    lookup: ScopeLookup,
    folder: str = ".",
    target: str | PurePath | ResourceIdentity | None = None,
    target_is_prospective: bool = False,
) -> ScopeBrowseResult:
    """Browse direct declaration-definition child folders only."""

    return _native.scope_browse(lookup, (folder, target, target_is_prospective))
