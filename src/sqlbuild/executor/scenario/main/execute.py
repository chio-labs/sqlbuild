"""Scenario model graph execution."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.types import TablePromotionMode
from sqlbuild.compiler.planner.models import ModelPlanEntry, ScenarioExecutionPlan
from sqlbuild.compiler.planner.types import MaterializationType, PlanAction
from sqlbuild.executor.run.main.execute import execute_table_entry, execute_view_entry
from sqlbuild.executor.run.models import ModelExecutionResult, ModelMaterializationContext
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.shared.constants import SCENARIO_EXEC_MODEL_FAILED


def execute_scenario_model(
    *,
    scenario_plan: ScenarioExecutionPlan,
    entry: ModelPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
    run_id: str,
) -> ModelExecutionResult:
    """Execute one scenario model entry against scenario-scoped relations."""

    if (
        entry.action == PlanAction.CUSTOM
        or entry.materialization_type == MaterializationType.CUSTOM
    ):
        return ModelExecutionResult(
            model_name=entry.name,
            status=ExecutionStatus.FAILED,
            error_code=SCENARIO_EXEC_MODEL_FAILED,
            error_help="Custom materializations are not supported in scenario runs yet.",
            error_message=(
                f"scenario '{scenario_plan.name}' model '{entry.name}' uses unsupported "
                "custom materialization"
            ),
        )

    if (
        entry.materialization_type == MaterializationType.VIEW
        or entry.action == PlanAction.CREATE_VIEW
    ):
        return _with_scenario_model_error_code(
            execute_view_entry(
                context=ModelMaterializationContext(
                    entry=entry,
                    adapter=adapter,
                    connection=connection,
                    model_locations=scenario_plan.relation_plan.model_locations,
                    seed_locations=scenario_plan.relation_plan.seed_locations,
                    source_map=scenario_plan.relation_plan.source_map,
                    model_audits=(),
                    run_id=run_id,
                    query_change_tracking=False,
                    hook_functions=scenario_plan.hook_functions,
                )
            )
        )

    table_entry: ModelPlanEntry = entry
    if entry.materialization_type == MaterializationType.INCREMENTAL:
        table_entry = replace(entry, action=PlanAction.CREATE_TABLE)

    return _with_scenario_model_error_code(
        execute_table_entry(
            context=ModelMaterializationContext(
                entry=table_entry,
                adapter=adapter,
                connection=connection,
                model_locations=scenario_plan.relation_plan.model_locations,
                seed_locations=scenario_plan.relation_plan.seed_locations,
                source_map=scenario_plan.relation_plan.source_map,
                model_audits=(),
                run_id=run_id,
                query_change_tracking=False,
                hook_functions=scenario_plan.hook_functions,
            ),
            declared_columns=entry.declared_columns,
            promotion_mode=TablePromotionMode.DIRECT,
        )
    )


def _with_scenario_model_error_code(result: ModelExecutionResult) -> ModelExecutionResult:
    if result.status != ExecutionStatus.FAILED:
        return result
    return replace(
        result,
        error_code=result.error_code or SCENARIO_EXEC_MODEL_FAILED,
        error_help=result.error_help
        or "Rerun with --retain to inspect scenario-owned relations and generated SQL.",
        error_message=f"scenario model '{result.model_name}' failed: {result.error_message}"
        if result.error_message is not None
        else f"scenario model '{result.model_name}' failed",
    )
