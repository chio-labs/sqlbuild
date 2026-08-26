"""Public pure scope report operation."""

from __future__ import annotations

from pathlib import PurePath

from sqlbuild.compiler.scopes._helpers.report_query import build_scope_report
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    ResourceIdentity,
    ScopeLookup,
    ScopeReport,
    ScopeReportFilters,
)


def query_scope_report(
    *,
    lookup: ScopeLookup,
    target: str | PurePath | ResourceIdentity | DeclarationIdentity | None = None,
    at: str | PurePath | None = None,
    directory: bool = False,
    filters: ScopeReportFilters | None = None,
) -> ScopeReport:
    """Query immutable compiler-owned scope facts without filesystem access."""

    return build_scope_report(
        lookup=lookup,
        target=target,
        at=at,
        directory=directory,
        filters=filters,
    )
