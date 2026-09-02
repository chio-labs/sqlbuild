"""Build execution orchestration over a planned execution schedule."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.compiler.planner.types import RetentionPlanPhase
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build._helpers.retention import (
    apply_retention_phase,
    apply_table_type_conversions,
    reconcile_retention_after_build,
)
from sqlbuild.executor.build.classes.build_scheduler import BuildScheduler
from sqlbuild.executor.build.main.aggregate_result import aggregate_build_result
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
from sqlbuild.executor.load.models import LoadExecutionResult
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
    schema_prepared: bool = False,
) -> BuildExecutionResult:
    """Execute a full build plan using the DAG scheduler."""

    resolved_callbacks: BuildCallbacks = callbacks if callbacks is not None else BuildCallbacks()
    resolved_customizations: BuildCustomizations = (
        customizations if customizations is not None else BuildCustomizations()
    )
    resolved_initial_state: BuildInitialState = (
        initial_state if initial_state is not None else BuildInitialState()
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
        schema_prepared=schema_prepared,
    )

    _ = apply_table_type_conversions(plan=plan, adapter=adapter, connection=scheduler_connection)
    _ = apply_retention_phase(
        plan=plan,
        adapter=adapter,
        connection=scheduler_connection,
        phase=RetentionPlanPhase.PRE,
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
        model_results=model_results,
        seed_results=seed_results,
        function_results=function_results,
        load_results=load_results,
        test_results=test_results,
        source_audit_results=source_audit_results,
        end_audit_results=end_audit_results,
    )
    if result.status == BuildStatus.SUCCESS:
        _ = reconcile_retention_after_build(
            plan=plan,
            adapter=adapter,
            connection=scheduler_connection,
        )
    return result
