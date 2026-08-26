"""Public canonical scope report serialization operation."""

from sqlbuild.compiler.scopes._helpers.report_operations import serialize_result
from sqlbuild.compiler.scopes.models import ScopeBrowseResult, ScopeListResult, ScopeReport


def serialize_scope_report(*, report: ScopeReport | ScopeBrowseResult | ScopeListResult) -> str:
    """Return deterministic schema-version-one JSON for any scope query result."""

    return serialize_result(result=report)
