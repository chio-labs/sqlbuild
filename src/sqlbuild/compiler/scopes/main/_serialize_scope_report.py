"""Public canonical scope report serialization operation."""

from sqlbuild.compiler.scopes._helpers.report_operations import serialize_report
from sqlbuild.compiler.scopes.models import ScopeReport


def serialize_scope_report(*, report: ScopeReport) -> str:
    """Return schema-version-one deterministic ASCII JSON with a trailing newline."""

    return serialize_report(report=report)
