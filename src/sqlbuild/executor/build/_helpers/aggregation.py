"""Build result aggregation helpers."""

from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.run.models import ModelExecutionResult


def count_insufficient_audits(
    *,
    model_results: tuple[ModelExecutionResult, ...],
    source_audit_results: tuple[AuditExecutionResult, ...],
    end_audit_results: tuple[AuditExecutionResult, ...],
) -> int:
    """Count visible non-blocking insufficient measurement outcomes."""

    results: list[AuditExecutionResult] = [*source_audit_results, *end_audit_results]
    for model_result in model_results:
        results.extend(model_result.audit_results)
    return sum(result.outcome == AuditOutcome.INSUFFICIENT for result in results)
