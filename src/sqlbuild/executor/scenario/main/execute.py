"""Scenario model graph execution."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.types import TablePromotionMode
from sqlbuild.compiler.planner.models import ModelPlanEntry, ScenarioExecutionPlan
from sqlbuild.compiler.planner.types import MaterializationType, PlanAction
from sqlbuild.executor.run.main.execute import execute_table_entry, execute_view_entry
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.types import ExecutionStatus


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
            error_message=(
                f"scenario '{scenario_plan.name}' model '{entry.name}' uses unsupported "
                "custom materialization"
            ),
        )

    if (
        entry.materialization_type == MaterializationType.VIEW
        or entry.action == PlanAction.CREATE_VIEW
    ):
        return execute_view_entry(
            entry=entry,
            adapter=adapter,
            connection=connection,
            model_targets=scenario_plan.relation_plan.model_targets,
            seed_targets=scenario_plan.relation_plan.seed_targets,
            source_map=scenario_plan.relation_plan.source_map,
            model_audits=(),
            run_id=run_id,
            query_change_tracking=False,
        )

    table_entry: ModelPlanEntry = entry
    if entry.materialization_type == MaterializationType.INCREMENTAL:
        table_entry = replace(entry, action=PlanAction.CREATE_TABLE)

    return execute_table_entry(
        entry=table_entry,
        adapter=adapter,
        connection=connection,
        model_targets=scenario_plan.relation_plan.model_targets,
        seed_targets=scenario_plan.relation_plan.seed_targets,
        source_map=scenario_plan.relation_plan.source_map,
        model_audits=(),
        declared_columns=entry.declared_columns,
        promotion_mode=TablePromotionMode.DIRECT,
        run_id=run_id,
        query_change_tracking=False,
    )
