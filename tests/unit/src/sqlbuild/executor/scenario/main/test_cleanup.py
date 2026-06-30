from __future__ import annotations

import pytest

from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.executor.scenario.main.operations.cleanup import execute_scenario_cleanup
from sqlbuild.executor.scenario.models import ScenarioCleanupExecutionResult
from sqlbuild.executor.shared.types import ExecutionStatus
from tests.unit.src.sqlbuild.executor.scenario.main._test_types import (
    ExecuteScenarioCleanupTestCase,
)
from tests.unit.src.sqlbuild.executor.scenario.main.helpers import (
    ScenarioFixtureTestAdapter,
    build_scenario_cleanup_test_plan,
    build_scenario_cleanup_test_plan_with_project_seed,
    executed_drop_sql,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ExecuteScenarioCleanupTestCase(
            description="drops only current scenario plan targets",
            expected_status=ExecutionStatus.SUCCESS,
            expected_drop_targets=(
                "scenario_schema.__sqb_51b385aebe20__source__raw__orders",
                "scenario_schema.__sqb_51b385aebe20__ref__stg_customers",
                "scenario_schema.__sqb_51b385aebe20__seed__country_codes",
                "scenario_schema.__sqb_51b385aebe20__model__daily_revenue",
            ),
            unexpected_drop_targets=(
                "scenario_schema.__sqb_51b385aebe20__model__stale_not_in_plan",
            ),
        )
    ],
    ids=["drops only current scenario plan targets"],
)
def test_given_scenario_plan_when_cleaning_up_then_drops_only_planned_targets(
    test_case: ExecuteScenarioCleanupTestCase,
) -> None:
    adapter: ScenarioFixtureTestAdapter = ScenarioFixtureTestAdapter()

    result: ScenarioCleanupExecutionResult = execute_scenario_cleanup(
        scenario_plan=build_scenario_cleanup_test_plan(),
        adapter=adapter,
        connection=object(),
    )

    assert result.status == test_case.expected_status
    assert (
        tuple(target.target_relation for target in result.targets)
        == test_case.expected_drop_targets
    )
    drop_sql: tuple[str, ...] = executed_drop_sql(adapter)
    for expected_target in test_case.expected_drop_targets:
        assert f"DROP TABLE IF EXISTS {expected_target}" in drop_sql
    for unexpected_target in test_case.unexpected_drop_targets:
        assert all(unexpected_target not in statement for statement in drop_sql)


@pytest.mark.parametrize(
    "test_case",
    [
        ExecuteScenarioCleanupTestCase(
            description="drops scenario view models as views",
            expected_status=ExecutionStatus.SUCCESS,
            expected_drop_targets=("scenario_schema.__sqb_51b385aebe20__model__daily_revenue",),
        )
    ],
    ids=["drops scenario view models as views"],
)
def test_given_view_model_in_scenario_plan_when_cleaning_up_then_drops_view(
    test_case: ExecuteScenarioCleanupTestCase,
) -> None:
    adapter: ScenarioFixtureTestAdapter = ScenarioFixtureTestAdapter()

    result: ScenarioCleanupExecutionResult = execute_scenario_cleanup(
        scenario_plan=build_scenario_cleanup_test_plan(
            model_materialization_type=MaterializationType.VIEW
        ),
        adapter=adapter,
        connection=object(),
    )

    assert result.status == test_case.expected_status
    drop_sql: tuple[str, ...] = executed_drop_sql(adapter)
    expected_target: str = test_case.expected_drop_targets[0]
    assert f"DROP VIEW IF EXISTS {expected_target}" in drop_sql
    assert f"DROP TABLE IF EXISTS {expected_target}" not in drop_sql


@pytest.mark.parametrize(
    "test_case",
    [
        ExecuteScenarioCleanupTestCase(
            description="returns failed cleanup result with target context",
            expected_status=ExecutionStatus.FAILED,
            expected_drop_targets=(
                "scenario_schema.__sqb_51b385aebe20__source__raw__orders",
                "scenario_schema.__sqb_51b385aebe20__ref__stg_customers",
                "scenario_schema.__sqb_51b385aebe20__seed__country_codes",
                "scenario_schema.__sqb_51b385aebe20__model__daily_revenue",
            ),
            expected_error_fragment="failed target __sqb_51b385aebe20__seed__country_codes",
        )
    ],
    ids=["returns failed cleanup result with target context"],
)
def test_given_adapter_failure_when_cleaning_up_then_returns_failed_result(
    test_case: ExecuteScenarioCleanupTestCase,
) -> None:
    adapter: ScenarioFixtureTestAdapter = ScenarioFixtureTestAdapter(
        fail_on_target="__sqb_51b385aebe20__seed__country_codes"
    )

    result: ScenarioCleanupExecutionResult = execute_scenario_cleanup(
        scenario_plan=build_scenario_cleanup_test_plan(),
        adapter=adapter,
        connection=object(),
    )

    assert result.status == test_case.expected_status
    assert (
        tuple(target.target_relation for target in result.targets)
        == test_case.expected_drop_targets
    )
    assert result.error_message == test_case.expected_error_fragment
    assert test_case.expected_error_fragment is not None
    assert test_case.expected_error_fragment in result.lifecycle_events[-1].content


@pytest.mark.parametrize(
    "test_case",
    [
        ExecuteScenarioCleanupTestCase(
            description="drops unmocked project seed target",
            expected_status=ExecutionStatus.SUCCESS,
            expected_drop_targets=(
                "scenario_schema.__sqb_51b385aebe20__source__raw__orders",
                "scenario_schema.__sqb_51b385aebe20__ref__stg_customers",
                "scenario_schema.__sqb_51b385aebe20__seed__country_codes",
                "scenario_schema.__sqb_51b385aebe20__model__daily_revenue",
            ),
        )
    ],
    ids=["drops unmocked project seed target"],
)
def test_given_unmocked_project_seed_when_cleaning_up_then_drops_seed_target(
    test_case: ExecuteScenarioCleanupTestCase,
) -> None:
    adapter: ScenarioFixtureTestAdapter = ScenarioFixtureTestAdapter()

    result: ScenarioCleanupExecutionResult = execute_scenario_cleanup(
        scenario_plan=build_scenario_cleanup_test_plan_with_project_seed(),
        adapter=adapter,
        connection=object(),
    )

    assert result.status == test_case.expected_status
    assert (
        tuple(target.target_relation for target in result.targets)
        == test_case.expected_drop_targets
    )
