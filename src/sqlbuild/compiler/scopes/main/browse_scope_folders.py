"""Public declaration folder browse operation."""

from pathlib import PurePath

from sqlbuild.compiler.scopes._helpers.report_operations import browse_folders
from sqlbuild.compiler.scopes.models import ResourceIdentity, ScopeBrowseResult, ScopeLookup


def browse_scope_folders(
    *,
    lookup: ScopeLookup,
    folder: str = ".",
    target: str | PurePath | ResourceIdentity | None = None,
    target_is_prospective: bool = False,
) -> ScopeBrowseResult:
    """Browse direct declaration-definition child folders only."""

    return browse_folders(
        lookup=lookup,
        folder=folder,
        target=target,
        target_is_prospective=target_is_prospective,
    )
