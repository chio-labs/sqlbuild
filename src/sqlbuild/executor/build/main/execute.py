"""Build execution orchestration over a planned execution schedule."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.node_source_watermarks.models import NodeSourceWatermarkExecutionContext
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build._helpers.node_source_watermarks import (
    build_native_node_source_watermark_context,
    write_native_node_source_watermark_records,
)
from sqlbuild.executor.build._helpers.output import aggregate_build_result
from sqlbuild.executor.build.classes.build_scheduler import BuildScheduler
from sqlbuild.executor.build.models import (
    BuildCallbacks,
    BuildCustomizations,
    BuildExecutionResult,
    BuildInitialState,
    BuildRuntimeParams,
    FunctionExecutionResult,
    SeedExecutionResult,
)
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.contracts.types import ExecutionStatus
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.run.main.dependency_baseline import execute_dependency_baseline_entries
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.testing.models import SqlTestExecutionResult


def execute_build_plan(
    *,
    plan: PlanOutput,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connections: tuple[Any, ...],
    scheduler_connection: Any,
    runtime: BuildRuntimeParams,
    callbacks: BuildCallbacks | None = None,
    customizations: BuildCustomizations | None = None,
    initial_state: BuildInitialState | None = None,
) -> BuildExecutionResult:
    """Execute a full build plan using the DAG scheduler."""

    resolved_callbacks: BuildCallbacks = callbacks if callbacks is not None else BuildCallbacks()
    resolved_customizations: BuildCustomizations = (
        customizations if customizations is not None else BuildCustomizations()
    )
    resolved_initial_state: BuildInitialState = (
        initial_state if initial_state is not None else BuildInitialState()
    )
    node_source_watermark_context: NodeSourceWatermarkExecutionContext | None = (
        build_native_node_source_watermark_context(
            plan=plan,
            adapter=adapter,
            connection=scheduler_connection,
        )
    )
    scheduler: BuildScheduler = BuildScheduler(
        plan=plan,
        adapter=adapter,
        connection_config=connection_config,
        connections=connections,
        scheduler_connection=scheduler_connection,
        runtime=runtime,
        callbacks=resolved_callbacks,
        customizations=resolved_customizations,
        initial_state=resolved_initial_state,
        node_source_watermark_context=node_source_watermark_context,
    )

    dependency_baseline_results: tuple[ModelExecutionResult, ...] = (
        execute_dependency_baseline_entries(
            entries=plan.dependency_baseline_entries,
            adapter=adapter,
            connection=scheduler_connection,
            on_node_start=resolved_callbacks.on_node_start,
            on_node_complete=resolved_callbacks.on_node_complete,
        )
    )
    if any(result.status == ExecutionStatus.FAILED for result in dependency_baseline_results):
        return aggregate_build_result(
            model_results=dependency_baseline_results,
            seed_results=(),
            function_results=(),
            load_results=resolved_initial_state.initial_load_results,
            test_results=(),
            source_audit_results=(),
            end_audit_results=(),
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

    result: BuildExecutionResult = aggregate_build_result(
        model_results=(*dependency_baseline_results, *model_results),
        seed_results=seed_results,
        function_results=function_results,
        load_results=load_results,
        test_results=test_results,
        source_audit_results=source_audit_results,
        end_audit_results=end_audit_results,
    )
    if result.status == BuildStatus.SUCCESS:
        write_native_node_source_watermark_records(
            context=node_source_watermark_context,
            adapter=adapter,
            connection=scheduler_connection,
        )
    return result
