"""Public declaration folder browse operation."""

from sqlbuild.compiler.scopes._helpers.report_operations import browse_folders
from sqlbuild.compiler.scopes.models import ScopeBrowseResult, ScopeLookup


def browse_scope_folders(*, lookup: ScopeLookup, folder: str = ".") -> ScopeBrowseResult:
    """Browse direct declaration-definition child folders only."""

    return browse_folders(lookup=lookup, folder=folder)
