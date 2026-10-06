from __future__ import annotations

import pytest

from sqlbuild.adapter.contract.types import TablePromotionMode
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.executor.scenario.main._cleanup import execute_scenario_cleanup
from sqlbuild.executor.scenario.main._run import execute_scenario_run
from sqlbuild.executor.scenario.models import ScenarioCleanupExecutionResult, ScenarioRunOptions
from sqlbuild.executor.scheduling.types import ExecutionStatus
from tests.unit.src.sqlbuild.executor.scenario.main._test_types import (
    ExecuteScenarioCleanupTestCase,
    ScenarioCatalogCleanupTestCase,
)
from tests.unit.src.sqlbuild.executor.scenario.main.helpers import (
    ScenarioCatalogTestAdapter,
    ScenarioFixtureTestAdapter,
    build_scenario_cleanup_test_plan,
    build_scenario_cleanup_test_plan_with_project_seed,
    executed_drop_sql,
)

_CATALOG_PREFIX: str = "scenario_schema.__sqb_51b385aebe20"


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
                "scenario_schema.__sqb_51b385aebe20__model__daily_revenue__staging",
            ),
            unexpected_drop_targets=(
                "scenario_schema.__sqb_51b385aebe20__model__stale_not_in_plan",
            ),
        )
    ],
    ids=lambda case: case.description,
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
    ids=lambda case: case.description,
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
    assert all("__staging" not in statement for statement in drop_sql)


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
                "scenario_schema.__sqb_51b385aebe20__model__daily_revenue__staging",
            ),
            expected_error_fragment="failed target __sqb_51b385aebe20__seed__country_codes",
        )
    ],
    ids=lambda case: case.description,
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
    ids=lambda case: case.description,
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


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioCatalogCleanupTestCase(
            description="drops only catalogued relations using the catalogued type",
            relation_types={
                "__sqb_51b385aebe20__source__raw__orders": "BASE TABLE",
                "__sqb_51b385aebe20__model__daily_revenue": "VIEW",
            },
            expected_drop_sql=(
                f"DROP TABLE IF EXISTS {_CATALOG_PREFIX}__source__raw__orders",
                f"DROP VIEW IF EXISTS {_CATALOG_PREFIX}__model__daily_revenue",
            ),
        ),
        ScenarioCatalogCleanupTestCase(
            description="issues no drops when nothing scenario-owned exists",
            relation_types={},
            expected_drop_sql=(),
        ),
        ScenarioCatalogCleanupTestCase(
            description="drops every planned target when the catalog cannot be read",
            relation_types={},
            fail_listing=True,
            expected_drop_sql=(
                f"DROP TABLE IF EXISTS {_CATALOG_PREFIX}__source__raw__orders",
                f"DROP TABLE IF EXISTS {_CATALOG_PREFIX}__ref__stg_customers",
                f"DROP TABLE IF EXISTS {_CATALOG_PREFIX}__seed__country_codes",
                f"DROP TABLE IF EXISTS {_CATALOG_PREFIX}__model__daily_revenue",
                f"DROP TABLE IF EXISTS {_CATALOG_PREFIX}__model__daily_revenue__staging",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_catalog_state_when_cleaning_up_then_drops_only_existing_relations(
    test_case: ScenarioCatalogCleanupTestCase,
) -> None:
    adapter: ScenarioCatalogTestAdapter = ScenarioCatalogTestAdapter(
        relation_types=test_case.relation_types, fail_listing=test_case.fail_listing
    )

    result: ScenarioCleanupExecutionResult = execute_scenario_cleanup(
        scenario_plan=build_scenario_cleanup_test_plan(),
        adapter=adapter,
        connection=object(),
    )

    assert result.status == ExecutionStatus.SUCCESS
    assert adapter.listing_count == 1
    assert executed_drop_sql(adapter) == test_case.expected_drop_sql


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioCatalogCleanupTestCase(
            description="interrupt drops relations created before it and reraises",
            relation_types={"__sqb_51b385aebe20__source__raw__orders": "BASE TABLE"},
            expected_drop_sql=(
                f"DROP TABLE IF EXISTS {_CATALOG_PREFIX}__source__raw__orders",
                f"DROP TABLE IF EXISTS {_CATALOG_PREFIX}__source__raw__orders",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_interrupt_during_scenario_when_running_then_cleans_up_and_reraises(
    test_case: ScenarioCatalogCleanupTestCase,
) -> None:
    adapter: ScenarioCatalogTestAdapter = ScenarioCatalogTestAdapter(
        relation_types=test_case.relation_types, interrupt_on_create=True
    )

    with pytest.raises(KeyboardInterrupt):
        _ = execute_scenario_run(
            scenario_plan=build_scenario_cleanup_test_plan(),
            adapter=adapter,
            connection=object(),
            run_id="run-1",
            retain=False,
            options=ScenarioRunOptions(promotion_mode=TablePromotionMode.STAGED),
        )

    assert adapter.listing_count == 2
    assert executed_drop_sql(adapter) == test_case.expected_drop_sql
