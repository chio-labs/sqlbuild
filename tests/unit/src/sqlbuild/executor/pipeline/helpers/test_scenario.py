"""Tests for scenario execution pipeline helpers."""

from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.compiler.compile.models import CompiledSqlScenario
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import ScenarioExecutionPlan
from sqlbuild.executor.pipeline.helpers import scenario as scenario_pipeline
from sqlbuild.executor.scenario.models import ScenarioRunResult
from sqlbuild.executor.shared.types import ExecutionStatus
from tests.unit.src.sqlbuild.executor.pipeline.helpers._test_types import (
    ScenarioTestPipelineTestCase,
)
from tests.unit.src.sqlbuild.executor.pipeline.helpers.helpers import (
    ScenarioPipelinePlanBuilder,
    ScenarioPipelineTestAdapter,
    build_scenario_pipeline_result,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioTestPipelineTestCase(
            description="continues after one scenario planning failure",
            scenario_names=("passing_scenario", "planning_failure"),
            planning_failure_name="planning_failure",
            expected_statuses=("success", "failed"),
            expected_started_names=("passing_scenario", "planning_failure"),
            expected_completed_names=("passing_scenario", "planning_failure"),
            expected_completed_plan_names=("passing_scenario", None),
            expected_connection_events=("connect:pipeline.duckdb", "close"),
            expected_error_fragment="scenario planning failed",
        ),
    ],
    ids=["continues after one scenario planning failure"],
)
def test_given_selected_scenarios_when_running_scenario_test_pipeline_then_orchestrates_batch(
    monkeypatch: pytest.MonkeyPatch,
    test_case: ScenarioTestPipelineTestCase,
) -> None:
    pipeline_result: CompilePipelineResult = build_scenario_pipeline_result(
        scenario_names=test_case.scenario_names,
    )
    adapter: ScenarioPipelineTestAdapter = ScenarioPipelineTestAdapter()
    started_names: list[str] = []
    completed_names: list[str] = []
    completed_plan_names: list[str | None] = []

    def execute_run(
        *,
        scenario_plan: ScenarioExecutionPlan,
        adapter: ScenarioPipelineTestAdapter,
        connection: Any,
        run_id: str,
        retain: bool,
    ) -> ScenarioRunResult:
        del adapter, connection, run_id, retain
        return ScenarioRunResult(
            scenario_name=scenario_plan.name,
            status=ExecutionStatus.SUCCESS,
        )

    def complete_scenario(
        scenario: CompiledSqlScenario,
        scenario_plan: ScenarioExecutionPlan | None,
        _result: ScenarioRunResult,
    ) -> None:
        completed_names.append(scenario.name)
        completed_plan_names.append(scenario_plan.name if scenario_plan is not None else None)

    monkeypatch.setattr(
        scenario_pipeline,
        "build_scenario_plan",
        ScenarioPipelinePlanBuilder(
            planning_failure_name=test_case.planning_failure_name,
            error_message=test_case.expected_error_fragment,
        ),
    )
    monkeypatch.setattr(scenario_pipeline, "execute_scenario_run", execute_run)

    results: tuple[ScenarioRunResult, ...] = scenario_pipeline.run_scenario_test_pipeline(
        pipeline_result=pipeline_result,
        scenarios=pipeline_result.project.sql_scenarios,
        connection_config={"database": "pipeline.duckdb"},
        adapter=adapter,
        project_name="waffle_shop",
        retain=False,
        on_scenario_start=lambda scenario: started_names.append(scenario.name),
        on_scenario_complete=complete_scenario,
    )

    assert tuple(result.status for result in results) == test_case.expected_statuses
    assert tuple(started_names) == test_case.expected_started_names
    assert tuple(completed_names) == test_case.expected_completed_names
    assert tuple(completed_plan_names) == test_case.expected_completed_plan_names
    assert tuple(adapter.events) == test_case.expected_connection_events
    assert results[-1].error_message is not None
    assert test_case.expected_error_fragment in results[-1].error_message
