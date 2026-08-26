"""Public recursive declaration folder list operation."""

from pathlib import PurePath

from sqlbuild.compiler.scopes._helpers.report_operations import list_folder
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

    return list_folder(
        lookup=lookup,
        folder=folder,
        filters=filters,
        target=target,
        target_is_prospective=target_is_prospective,
    )
