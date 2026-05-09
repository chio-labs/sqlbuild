from __future__ import annotations

import pytest

from sqlbuild.adapter.shared.types import LifeCycleEventKind
from sqlbuild.compiler.planner.models import ScenarioFixturePlan
from sqlbuild.compiler.planner.types import ScenarioArtifactKind
from sqlbuild.executor.scenario.helpers.fixtures import execute_scenario_fixtures
from sqlbuild.executor.scenario.main.fixtures import execute_scenario_fixture
from sqlbuild.executor.scenario.models import ScenarioFixtureExecutionResult
from sqlbuild.executor.shared.types import ExecutionStatus
from tests.unit.src.sqlbuild.executor.scenario.main._test_types import (
    ExecuteScenarioFixturesTestCase,
    ExecuteScenarioFixtureTestCase,
)
from tests.unit.src.sqlbuild.executor.scenario.main.helpers import (
    ScenarioFixtureTestAdapter,
    build_scenario_fixture_plan,
    executed_create_table_sql,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ExecuteScenarioFixtureTestCase(
            description="materializes fixture SQL into scenario target table",
            scenario_name="revenue__customer_refund",
            expected_status=ExecutionStatus.SUCCESS,
            expected_target_relation="scenario_schema.__sqb_51b385aebe20__source__raw__orders",
            expected_sql_fragment=(
                "WITH helper_orders AS (SELECT 1 AS order_id) SELECT * FROM helper_orders"
            ),
        )
    ],
    ids=["materializes fixture SQL into scenario target table"],
)
def test_given_scenario_fixture_plan_when_executing_then_creates_scenario_table(
    test_case: ExecuteScenarioFixtureTestCase,
) -> None:
    adapter: ScenarioFixtureTestAdapter = ScenarioFixtureTestAdapter()

    result: ScenarioFixtureExecutionResult = execute_scenario_fixture(
        scenario_name=test_case.scenario_name,
        fixture_plan=build_scenario_fixture_plan(),
        adapter=adapter,
        connection=object(),
    )

    assert result.status == test_case.expected_status
    assert result.target_relation == test_case.expected_target_relation
    assert result.error_message == test_case.expected_error_fragment
    assert len(executed_create_table_sql(adapter)) == 1
    assert test_case.expected_target_relation in executed_create_table_sql(adapter)[0]
    assert test_case.expected_sql_fragment in executed_create_table_sql(adapter)[0]
    assert tuple(event.kind for event in result.lifecycle_events) == (
        LifeCycleEventKind.SQL,
        LifeCycleEventKind.SQL,
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ExecuteScenarioFixtureTestCase(
            description="returns failed result with fixture context on create failure",
            scenario_name="revenue__customer_refund",
            expected_status=ExecutionStatus.FAILED,
            expected_target_relation="scenario_schema.__sqb_51b385aebe20__source__raw__orders",
            expected_sql_fragment="failed target __sqb_51b385aebe20__source__raw__orders",
            expected_error_fragment="failed target __sqb_51b385aebe20__source__raw__orders",
        )
    ],
    ids=["returns failed result with fixture context on create failure"],
)
def test_given_adapter_failure_when_executing_fixture_then_returns_failed_result(
    test_case: ExecuteScenarioFixtureTestCase,
) -> None:
    adapter: ScenarioFixtureTestAdapter = ScenarioFixtureTestAdapter(
        fail_on_target="__sqb_51b385aebe20__source__raw__orders"
    )

    result: ScenarioFixtureExecutionResult = execute_scenario_fixture(
        scenario_name=test_case.scenario_name,
        fixture_plan=build_scenario_fixture_plan(),
        adapter=adapter,
        connection=object(),
    )

    assert result.status == test_case.expected_status
    assert result.target_relation == test_case.expected_target_relation
    assert result.error_message == test_case.expected_error_fragment
    assert test_case.expected_sql_fragment in result.lifecycle_events[-1].content
    assert "revenue__customer_refund:source:raw__orders" in result.lifecycle_events[-1].content


@pytest.mark.parametrize(
    "test_case",
    [
        ExecuteScenarioFixturesTestCase(
            description="stops fixture execution after first failure",
            expected_result_count=1,
            expected_statuses=(ExecutionStatus.FAILED,),
            expected_executed_target_count=1,
        )
    ],
    ids=["stops fixture execution after first failure"],
)
def test_given_fixture_failure_when_executing_fixtures_then_stops_before_next_fixture(
    test_case: ExecuteScenarioFixturesTestCase,
) -> None:
    adapter: ScenarioFixtureTestAdapter = ScenarioFixtureTestAdapter(
        fail_on_target="__sqb_51b385aebe20__source__raw__orders"
    )
    fixture_plans: tuple[ScenarioFixturePlan, ...] = (
        build_scenario_fixture_plan(),
        build_scenario_fixture_plan(
            kind=ScenarioArtifactKind.REF,
            logical_name="stg_customers",
            target_name="__sqb_51b385aebe20__ref__stg_customers",
            sql="SELECT 10 AS customer_id",
        ),
    )

    results: tuple[ScenarioFixtureExecutionResult, ...] = execute_scenario_fixtures(
        scenario_name="revenue__customer_refund",
        fixture_plans=fixture_plans,
        adapter=adapter,
        connection=object(),
    )

    assert len(results) == test_case.expected_result_count
    assert tuple(result.status for result in results) == test_case.expected_statuses
    assert len(executed_create_table_sql(adapter)) == test_case.expected_executed_target_count
