"""Public canonical scope report serialization operation."""

import sqlbuild._native as _native
from sqlbuild.compiler.scopes.models import ScopeBrowseResult, ScopeListResult, ScopeReport


def serialize_scope_report(*, report: ScopeReport | ScopeBrowseResult | ScopeListResult) -> str:
    """Return deterministic schema-version-one JSON for any scope query result."""

    return _native.serialize_scope_report(report)
