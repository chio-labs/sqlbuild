"""Build execution orchestration over a planned execution schedule."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.adapter.shared.types import TablePromotionMode
from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build.helpers.indexes import build_execution_indexes
from sqlbuild.executor.build.helpers.scheduler import BuildScheduler
from sqlbuild.executor.build.models import BuildExecutionResult, BuildIndexes, SeedExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.custom.models import MaterializationResult
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.executor.testing.models import SqlTestExecutionResult
from sqlbuild.executor.testing.types import SqlTestOutcome


def execute_build_plan(
    *,
    plan: PlanOutput,
    adapter: BaseAdapter,
    connections: tuple[Any, ...],
    scheduler_connection: Any,
    promotion_mode: TablePromotionMode,
    run_id: str,
    query_change_tracking: bool = True,
    run_audits: bool = True,
    run_tests: bool = True,
    fail_fast: bool = False,
    on_progress: Callable[[str], None] | None = None,
    on_node_start: Callable[[str, str], None] | None = None,
    on_node_complete: Callable[[object], None] | None = None,
    custom_materializations: dict[str, Callable[..., MaterializationResult]] | None = None,
    environment: str = "",
    effective_vars: dict[str, str] | None = None,
    warehouse_relations: dict[str, RelationInfo] | None = None,
    on_sub_progress: Callable[[str], None] | None = None,
) -> BuildExecutionResult:
    """Execute a full build plan using the DAG scheduler."""

    indexes: BuildIndexes = build_execution_indexes(plan)
    scheduler: BuildScheduler = BuildScheduler(
        plan=plan,
        indexes=indexes,
        adapter=adapter,
        connections=connections,
        scheduler_connection=scheduler_connection,
        promotion_mode=promotion_mode,
        run_id=run_id,
        query_change_tracking=query_change_tracking,
        run_audits=run_audits,
        run_tests=run_tests,
        fail_fast=fail_fast,
        on_node_start=on_node_start,
        on_node_complete=on_node_complete,
        on_progress=on_progress,
        custom_materializations=custom_materializations,
        environment=environment,
        effective_vars=effective_vars,
        warehouse_relations=warehouse_relations,
        on_sub_progress=on_sub_progress,
    )

    model_results: tuple[ModelExecutionResult, ...]
    seed_results: tuple[SeedExecutionResult, ...]
    test_results: tuple[SqlTestExecutionResult, ...]
    source_audit_results: tuple[AuditExecutionResult, ...]
    end_audit_results: tuple[AuditExecutionResult, ...]
    (
        model_results,
        seed_results,
        test_results,
        source_audit_results,
        end_audit_results,
    ) = scheduler.run()

    return _aggregate_build_result(
        model_results=model_results,
        seed_results=seed_results,
        test_results=test_results,
        source_audit_results=source_audit_results,
        end_audit_results=end_audit_results,
    )


def _aggregate_build_result(
    *,
    model_results: tuple[ModelExecutionResult, ...],
    seed_results: tuple[SeedExecutionResult, ...],
    test_results: tuple[SqlTestExecutionResult, ...],
    source_audit_results: tuple[AuditExecutionResult, ...],
    end_audit_results: tuple[AuditExecutionResult, ...],
) -> BuildExecutionResult:
    """Compute aggregate counts and overall build status."""

    success_count: int = 0
    failure_count: int = 0
    skipped_count: int = 0
    warning_count: int = 0

    model_result: ModelExecutionResult
    for model_result in model_results:
        if model_result.status == ExecutionStatus.SUCCESS:
            success_count += 1
        elif model_result.status == ExecutionStatus.FAILED:
            failure_count += 1
        elif model_result.status == ExecutionStatus.SKIPPED:
            skipped_count += 1
        warning_count += len(model_result.warning_messages)
        audit_result: AuditExecutionResult
        for audit_result in model_result.audit_results:
            if audit_result.outcome == AuditOutcome.WARN:
                warning_count += 1

    seed_result: SeedExecutionResult
    for seed_result in seed_results:
        if seed_result.status == ExecutionStatus.SUCCESS:
            success_count += 1
        elif seed_result.status == ExecutionStatus.FAILED:
            failure_count += 1
        elif seed_result.status == ExecutionStatus.SKIPPED:
            skipped_count += 1

    test_result_entry: SqlTestExecutionResult
    for test_result_entry in test_results:
        if test_result_entry.outcome == SqlTestOutcome.PASS:
            success_count += 1
        else:
            failure_count += 1

    any_end_error: bool = False
    end_result: AuditExecutionResult
    for end_result in end_audit_results:
        if end_result.outcome == AuditOutcome.ERROR:
            any_end_error = True
        elif end_result.outcome == AuditOutcome.WARN:
            warning_count += 1

    source_result: AuditExecutionResult
    for source_result in source_audit_results:
        if source_result.outcome == AuditOutcome.ERROR:
            failure_count += 1
        elif source_result.outcome == AuditOutcome.WARN:
            warning_count += 1

    overall_failed: bool = failure_count > 0 or any_end_error
    status: BuildStatus = BuildStatus.FAILED if overall_failed else BuildStatus.SUCCESS

    return BuildExecutionResult(
        status=status,
        model_results=model_results,
        seed_results=seed_results,
        test_results=test_results,
        source_audit_results=source_audit_results,
        end_audit_results=end_audit_results,
        success_count=success_count,
        failure_count=failure_count,
        skipped_count=skipped_count,
        warning_count=warning_count,
    )
