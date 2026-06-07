"""Build execution orchestration over a planned execution schedule."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.adapter.shared.types import TablePromotionMode
from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.compiler.planner.models import ModelPlanEntry, PlanOutput
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build.helpers.indexes import build_execution_indexes
from sqlbuild.executor.build.helpers.scheduler import BuildScheduler
from sqlbuild.executor.build.models import (
    BuildExecutionResult,
    BuildIndexes,
    FunctionExecutionResult,
    SeedExecutionResult,
)
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.custom.models import MaterializationResult
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.executor.testing.models import SqlTestExecutionResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from sqlbuild.provider.main.runtime import ProviderContainer
from sqlbuild.shared.types import ExecutionResourceKind
from sqlbuild.spec.models.project import SnapshotsConfig


def execute_build_plan(
    *,
    plan: PlanOutput,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connections: tuple[Any, ...],
    scheduler_connection: Any,
    promotion_mode: TablePromotionMode,
    run_id: str,
    query_change_tracking: bool = True,
    snapshots: SnapshotsConfig | None = None,
    allow_snapshot_schema_change: bool = False,
    run_audits: bool = True,
    run_tests: bool = True,
    fail_fast: bool = False,
    on_progress: Callable[[str], None] | None = None,
    on_node_start: Callable[[str, ExecutionResourceKind], None] | None = None,
    on_node_complete: Callable[[object], None] | None = None,
    before_model_materialize: Callable[[ModelPlanEntry, Any], None] | None = None,
    custom_materializations: Mapping[str, Callable[..., MaterializationResult]] | None = None,
    loader_functions: tuple[DiscoveredLoaderFunction, ...] = (),
    loader_is_reload: bool = False,
    start_cursor_ts: datetime | None = None,
    end_cursor_ts: datetime | None = None,
    start_cursor_int: int | None = None,
    end_cursor_int: int | None = None,
    target: str = "",
    effective_vars: dict[str, object] | None = None,
    warehouse_relations: dict[str, RelationInfo] | None = None,
    on_sub_progress: Callable[[str], None] | None = None,
    use_color: bool = False,
    precompleted_keys: frozenset[CompiledObjectKey] = frozenset(),
    initial_load_results: tuple[LoadExecutionResult, ...] = (),
    initial_failed_keys: frozenset[CompiledObjectKey] = frozenset(),
    providers: ProviderContainer | None = None,
) -> BuildExecutionResult:
    """Execute a full build plan using the DAG scheduler."""

    indexes: BuildIndexes = build_execution_indexes(plan)
    scheduler: BuildScheduler = BuildScheduler(
        plan=plan,
        indexes=indexes,
        adapter=adapter,
        connection_config=connection_config,
        connections=connections,
        scheduler_connection=scheduler_connection,
        promotion_mode=promotion_mode,
        run_id=run_id,
        query_change_tracking=query_change_tracking,
        snapshots=snapshots or SnapshotsConfig(),
        allow_snapshot_schema_change=allow_snapshot_schema_change,
        run_audits=run_audits,
        run_tests=run_tests,
        fail_fast=fail_fast,
        on_node_start=on_node_start,
        on_node_complete=on_node_complete,
        on_progress=on_progress,
        before_model_materialize=before_model_materialize,
        custom_materializations=custom_materializations,
        loader_functions=loader_functions,
        loader_is_reload=loader_is_reload,
        start_cursor_ts=start_cursor_ts,
        end_cursor_ts=end_cursor_ts,
        start_cursor_int=start_cursor_int,
        end_cursor_int=end_cursor_int,
        target=target,
        effective_vars=effective_vars,
        warehouse_relations=warehouse_relations,
        on_sub_progress=on_sub_progress,
        use_color=use_color,
        precompleted_keys=precompleted_keys,
        initial_load_results=initial_load_results,
        initial_failed_keys=initial_failed_keys,
        providers=providers,
    )

    model_results: tuple[ModelExecutionResult, ...]
    seed_results: tuple[SeedExecutionResult, ...]
    function_results: tuple[FunctionExecutionResult, ...]
    load_results: tuple[LoadExecutionResult, ...]
    test_results: tuple[SqlTestExecutionResult, ...]
    source_audit_results: tuple[AuditExecutionResult, ...]
    end_audit_results: tuple[AuditExecutionResult, ...]
    (
        model_results,
        seed_results,
        function_results,
        load_results,
        test_results,
        source_audit_results,
        end_audit_results,
    ) = scheduler.run()

    return _aggregate_build_result(
        model_results=model_results,
        seed_results=seed_results,
        function_results=function_results,
        load_results=load_results,
        test_results=test_results,
        source_audit_results=source_audit_results,
        end_audit_results=end_audit_results,
    )


def _aggregate_build_result(
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

    function_result: FunctionExecutionResult
    for function_result in function_results:
        if function_result.status == ExecutionStatus.SUCCESS:
            success_count += 1
        elif function_result.status == ExecutionStatus.FAILED:
            failure_count += 1
        elif function_result.status == ExecutionStatus.SKIPPED:
            skipped_count += 1
        warning_count += len(function_result.warning_messages)

    load_result: LoadExecutionResult
    for load_result in load_results:
        if load_result.status == ExecutionStatus.SUCCESS:
            success_count += 1
        elif load_result.status == ExecutionStatus.FAILED:
            failure_count += 1
        elif load_result.status == ExecutionStatus.SKIPPED:
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
        function_results=function_results,
        load_results=load_results,
        test_results=test_results,
        source_audit_results=source_audit_results,
        end_audit_results=end_audit_results,
        success_count=success_count,
        failure_count=failure_count,
        skipped_count=skipped_count,
        warning_count=warning_count,
    )
