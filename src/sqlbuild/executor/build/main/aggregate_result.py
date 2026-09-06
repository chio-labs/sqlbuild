"""Public entry for typed build result aggregation."""

from __future__ import annotations

from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build._helpers.aggregation import count_insufficient_audits
from sqlbuild.executor.build.constants import BUILD_SOURCE_FRESHNESS_BLOCKED_CODE
from sqlbuild.executor.build.models import (
    BuildExecutionResult,
    FunctionExecutionResult,
    SeedExecutionResult,
)
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.executor.testing.models import SqlTestExecutionResult
from sqlbuild.executor.testing.types import SqlTestOutcome


def aggregate_build_result(
    *,
    model_results: tuple[ModelExecutionResult, ...],
    seed_results: tuple[SeedExecutionResult, ...],
    function_results: tuple[FunctionExecutionResult, ...],
    load_results: tuple[LoadExecutionResult, ...],
    test_results: tuple[SqlTestExecutionResult, ...],
    source_audit_results: tuple[AuditExecutionResult, ...],
    end_audit_results: tuple[AuditExecutionResult, ...],
) -> BuildExecutionResult:
    """Compute aggregate counts and overall build status."""

    resource_counts: tuple[int, int, int, int] = _aggregate_resources(
        model_results=model_results,
        seed_results=seed_results,
        function_results=function_results,
        load_results=load_results,
        test_results=test_results,
    )
    success_count: int = resource_counts[0]
    failure_count: int = resource_counts[1]
    skipped_count: int = resource_counts[2]
    warning_count: int = resource_counts[3]
    insufficient_count: int = count_insufficient_audits(
        model_results=model_results,
        source_audit_results=source_audit_results,
        end_audit_results=end_audit_results,
    )
    audit_counts: tuple[int, int, bool] = _aggregate_audits(
        source_audit_results=source_audit_results,
        end_audit_results=end_audit_results,
    )
    failure_count += audit_counts[0]
    warning_count += audit_counts[1]
    status: BuildStatus = (
        BuildStatus.FAILED if failure_count > 0 or audit_counts[2] else BuildStatus.SUCCESS
    )
    return BuildExecutionResult(
        status=status,
        model_results=model_results,
        seed_results=seed_results,
        function_results=function_results,
        load_results=load_results,
        test_results=test_results,
        source_audit_results=source_audit_results,
        end_audit_results=end_audit_results,
        success_count=success_count,
        failure_count=failure_count,
        skipped_count=skipped_count,
        warning_count=warning_count,
        insufficient_count=insufficient_count,
    )


def _aggregate_resources(
    *,
    model_results: tuple[ModelExecutionResult, ...],
    seed_results: tuple[SeedExecutionResult, ...],
    function_results: tuple[FunctionExecutionResult, ...],
    load_results: tuple[LoadExecutionResult, ...],
    test_results: tuple[SqlTestExecutionResult, ...],
) -> tuple[int, int, int, int]:
    success_count: int = 0
    failure_count: int = 0
    skipped_count: int = 0
    warning_count: int = 0
    for model_result in model_results:
        if model_result.status == ExecutionStatus.SUCCESS:
            success_count += 1
        elif model_result.status == ExecutionStatus.FAILED:
            failure_count += 1
        elif model_result.status == ExecutionStatus.SKIPPED:
            skipped_count += 1
            if model_result.error_code == BUILD_SOURCE_FRESHNESS_BLOCKED_CODE:
                failure_count += 1
        warning_count += len(model_result.warning_messages)
        warning_count += sum(
            audit_result.outcome == AuditOutcome.WARN for audit_result in model_result.audit_results
        )
    for seed_result in seed_results:
        success_count += seed_result.status == ExecutionStatus.SUCCESS
        failure_count += seed_result.status == ExecutionStatus.FAILED
        skipped_count += seed_result.status == ExecutionStatus.SKIPPED
    for function_result in function_results:
        success_count += function_result.status == ExecutionStatus.SUCCESS
        failure_count += function_result.status == ExecutionStatus.FAILED
        skipped_count += function_result.status == ExecutionStatus.SKIPPED
        warning_count += len(function_result.warning_messages)
    for load_result in load_results:
        success_count += load_result.status == ExecutionStatus.SUCCESS
        failure_count += load_result.status == ExecutionStatus.FAILED
        skipped_count += load_result.status == ExecutionStatus.SKIPPED
    for test_result in test_results:
        success_count += test_result.outcome == SqlTestOutcome.PASS
        failure_count += test_result.outcome != SqlTestOutcome.PASS
    return success_count, failure_count, skipped_count, warning_count


def _aggregate_audits(
    *,
    source_audit_results: tuple[AuditExecutionResult, ...],
    end_audit_results: tuple[AuditExecutionResult, ...],
) -> tuple[int, int, bool]:
    source_failures: int = sum(
        result.outcome == AuditOutcome.ERROR for result in source_audit_results
    )
    warnings: int = sum(
        result.outcome == AuditOutcome.WARN
        for result in (*source_audit_results, *end_audit_results)
    )
    any_end_error: bool = any(result.outcome == AuditOutcome.ERROR for result in end_audit_results)
    return source_failures, warnings, any_end_error
