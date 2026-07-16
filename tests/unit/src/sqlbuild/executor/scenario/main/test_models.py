from __future__ import annotations

import pytest

from sqlbuild.compiler.planner.models import ModelPlanEntry, ScenarioExecutionPlan
from sqlbuild.compiler.planner.types import MaterializationType, PlanAction
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.scenario._helpers.execution.model_execution import execute_scenario_models
from sqlbuild.executor.scenario.main.execute import execute_scenario_model
from sqlbuild.executor.scheduling.types import ExecutionStatus
from tests.unit.src.sqlbuild.executor.scenario.main._test_types import (
    ExecuteScenarioModelsTestCase,
)
from tests.unit.src.sqlbuild.executor.scenario.main.helpers import (
    ScenarioFixtureTestAdapter,
    build_scenario_model_entry,
    build_scenario_model_test_plan,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ExecuteScenarioModelsTestCase(
            description="creates scenario table model from resolved scenario SQL",
            expected_statuses=(ExecutionStatus.SUCCESS,),
            expected_model_names=("daily_revenue",),
            expected_sql_fragments=(
                "CREATE OR REPLACE TABLE scenario_schema.__sqb_51b385aebe20__model__daily_revenue",
                "scenario_schema.__sqb_51b385aebe20__source__raw__orders",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_table_model_entry_when_executing_scenario_model_then_creates_table(
    test_case: ExecuteScenarioModelsTestCase,
) -> None:
    entry: ModelPlanEntry = build_scenario_model_entry()
    scenario_plan: ScenarioExecutionPlan = build_scenario_model_test_plan(model_entries=(entry,))
    adapter: ScenarioFixtureTestAdapter = ScenarioFixtureTestAdapter()

    result: ModelExecutionResult = execute_scenario_model(
        scenario_plan=scenario_plan,
        entry=entry,
        adapter=adapter,
        connection=object(),
        run_id="run-1",
    )

    assert result.status == test_case.expected_statuses[0]
    assert result.model_name == test_case.expected_model_names[0]
    for expected_fragment in test_case.expected_sql_fragments:
        assert any(expected_fragment in statement for statement in adapter.executed_sql)


@pytest.mark.parametrize(
    "test_case",
    [
        ExecuteScenarioModelsTestCase(
            description="creates scenario view model",
            expected_statuses=(ExecutionStatus.SUCCESS,),
            expected_model_names=("daily_revenue",),
            expected_sql_fragments=(
                "CREATE OR REPLACE VIEW scenario_schema.__sqb_51b385aebe20__model__daily_revenue",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_view_model_entry_when_executing_scenario_model_then_creates_view(
    test_case: ExecuteScenarioModelsTestCase,
) -> None:
    entry: ModelPlanEntry = build_scenario_model_entry(
        materialization_type=MaterializationType.VIEW,
        action=PlanAction.CREATE_VIEW,
    )
    scenario_plan: ScenarioExecutionPlan = build_scenario_model_test_plan(model_entries=(entry,))
    adapter: ScenarioFixtureTestAdapter = ScenarioFixtureTestAdapter()

    result: ModelExecutionResult = execute_scenario_model(
        scenario_plan=scenario_plan,
        entry=entry,
        adapter=adapter,
        connection=object(),
        run_id="run-1",
    )

    assert result.status == test_case.expected_statuses[0]
    assert result.model_name == test_case.expected_model_names[0]
    for expected_fragment in test_case.expected_sql_fragments:
        assert any(expected_fragment in statement for statement in adapter.executed_sql)


@pytest.mark.parametrize(
    "test_case",
    [
        ExecuteScenarioModelsTestCase(
            description="runs incremental model as full refresh scenario table",
            expected_statuses=(ExecutionStatus.SUCCESS,),
            expected_model_names=("daily_revenue",),
            expected_sql_fragments=(
                "CREATE OR REPLACE TABLE scenario_schema.__sqb_51b385aebe20__model__daily_revenue",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_incremental_model_entry_when_executing_scenario_model_then_creates_table(
    test_case: ExecuteScenarioModelsTestCase,
) -> None:
    entry: ModelPlanEntry = build_scenario_model_entry(
        materialization_type=MaterializationType.INCREMENTAL,
        action=PlanAction.INCREMENTAL_MERGE,
    )
    scenario_plan: ScenarioExecutionPlan = build_scenario_model_test_plan(model_entries=(entry,))
    adapter: ScenarioFixtureTestAdapter = ScenarioFixtureTestAdapter()

    result: ModelExecutionResult = execute_scenario_model(
        scenario_plan=scenario_plan,
        entry=entry,
        adapter=adapter,
        connection=object(),
        run_id="run-1",
    )

    assert result.status == test_case.expected_statuses[0]
    assert result.model_name == test_case.expected_model_names[0]
    for expected_fragment in test_case.expected_sql_fragments:
        assert any(expected_fragment in statement for statement in adapter.executed_sql)


@pytest.mark.parametrize(
    "test_case",
    [
        ExecuteScenarioModelsTestCase(
            description="stops scenario model execution after first failure",
            expected_statuses=(ExecutionStatus.FAILED,),
            expected_model_names=("stg_orders",),
            expected_sql_fragments=("scenario_schema.__sqb_51b385aebe20__model__stg_orders",),
            expected_error_fragment="failed target __sqb_51b385aebe20__model__stg_orders",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_model_failure_when_executing_scenario_models_then_stops_before_next_model(
    test_case: ExecuteScenarioModelsTestCase,
) -> None:
    first_entry: ModelPlanEntry = build_scenario_model_entry(
        name="stg_orders",
        target_name="__sqb_51b385aebe20__model__stg_orders",
    )
    second_entry: ModelPlanEntry = build_scenario_model_entry()
    scenario_plan: ScenarioExecutionPlan = build_scenario_model_test_plan(
        model_entries=(first_entry, second_entry)
    )
    adapter: ScenarioFixtureTestAdapter = ScenarioFixtureTestAdapter(
        fail_on_target="__sqb_51b385aebe20__model__stg_orders"
    )

    results: tuple[ModelExecutionResult, ...] = execute_scenario_models(
        scenario_plan=scenario_plan,
        adapter=adapter,
        connection=object(),
        run_id="run-1",
    )

    assert tuple(result.status for result in results) == test_case.expected_statuses
    assert tuple(result.model_name for result in results) == test_case.expected_model_names
    assert results[0].error_message is not None
    assert test_case.expected_error_fragment is not None
    assert test_case.expected_error_fragment in results[0].error_message
    for expected_fragment in test_case.expected_sql_fragments:
        assert any(expected_fragment in statement for statement in adapter.executed_sql)
    assert all(
        "__sqb_51b385aebe20__model__daily_revenue" not in sql for sql in adapter.executed_sql
    )
