"""Public recursive declaration folder list operation."""

from sqlbuild.compiler.scopes._helpers.report_operations import list_folder
from sqlbuild.compiler.scopes.models import ScopeListResult, ScopeLookup, ScopeReportFilters


def list_scope_declarations(
    *, lookup: ScopeLookup, folder: str, filters: ScopeReportFilters | None = None
) -> ScopeListResult:
    """List declarations recursively beneath one browsed folder."""

    return list_folder(lookup=lookup, folder=folder, filters=filters)
