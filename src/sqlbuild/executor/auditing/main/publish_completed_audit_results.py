"""Incremental audit completion publication entrypoint."""

from __future__ import annotations

from sqlbuild.executor.auditing._helpers.result_projection import (
    publish_completed_audit_results_impl,
)
from sqlbuild.executor.auditing.models import AuditExecutionResult


def publish_completed_audit_results(results: tuple[AuditExecutionResult, ...]) -> None:
    """Publish confirmed, non-reused audit outcomes once; no-op outside a publication scope."""

    return publish_completed_audit_results_impl(results)
