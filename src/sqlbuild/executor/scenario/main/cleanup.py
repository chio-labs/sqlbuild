"""Scenario cleanup execution."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.compiler.planner.models import ScenarioExecutionPlan
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.diagnostics.main.diagnostics_context import diagnostics_context
from sqlbuild.executor.scenario._helpers.lifecycle.cleanup import collect_scenario_cleanup_targets
from sqlbuild.executor.scenario.constants import SCENARIO_EXEC_CLEANUP_FAILED
from sqlbuild.executor.scenario.models import (
    ScenarioCleanupExecutionResult,
    ScenarioCleanupTarget,
)
from sqlbuild.executor.types import ExecutionStatus


def execute_scenario_cleanup(
    *,
    scenario_plan: ScenarioExecutionPlan,
    adapter: BaseAdapter,
    connection: Any,
) -> ScenarioCleanupExecutionResult:
    """Drop only scenario-owned relations listed in the current scenario plan."""

    statement_recorder: StatementRecorder = StatementRecorder()
    cleanup_targets: tuple[ScenarioCleanupTarget, ...] = collect_scenario_cleanup_targets(
        scenario_plan=scenario_plan,
        adapter=adapter,
    )

    try:
        cleanup_target: ScenarioCleanupTarget
        for cleanup_target in cleanup_targets:
            with diagnostics_context(
                sqlbuild_phase="scenario_cleanup",
                sqlbuild_action_name="drop_relation",
                sqlbuild_scenario=scenario_plan.name,
                sqlbuild_artifact_kind=cleanup_target.kind.value,
                sqlbuild_artifact_name=cleanup_target.logical_name,
            ):
                if cleanup_target.materialization_type == MaterializationType.VIEW:
                    adapter.drop_view(
                        connection=connection,
                        destination=cleanup_target.target_relation,
                        if_exists=True,
                        statement_recorder=statement_recorder,
                    )
                else:
                    adapter.drop(
                        connection=connection,
                        destination=cleanup_target.target_relation,
                        if_exists=True,
                        statement_recorder=statement_recorder,
                    )
    except Exception as exc:
        statement_recorder.log(f"scenario cleanup {scenario_plan.name} failed error={exc}")
        return ScenarioCleanupExecutionResult(
            scenario_name=scenario_plan.name,
            status=ExecutionStatus.FAILED,
            targets=cleanup_targets,
            lifecycle_events=statement_recorder.snapshot(),
            error_code=SCENARIO_EXEC_CLEANUP_FAILED,
            error_help="Drop retained scenario artifacts manually or rerun `sqb janitor`.",
            error_message=str(exc),
        )

    return ScenarioCleanupExecutionResult(
        scenario_name=scenario_plan.name,
        status=ExecutionStatus.SUCCESS,
        targets=cleanup_targets,
        lifecycle_events=statement_recorder.snapshot(),
    )
