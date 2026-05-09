from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledRelationTarget
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import (
    ScenarioExecutionPlan,
    ScenarioFixturePlan,
    SeedPlanEntry,
)
from sqlbuild.executor.build.models import SeedExecutionResult
from sqlbuild.executor.scenario.helpers.fixtures import (
    execute_scenario_fixtures,
    execute_scenario_seed_entries,
)
from sqlbuild.executor.scenario.main.cleanup import execute_scenario_cleanup
from sqlbuild.executor.scenario.main.fixtures import execute_scenario_fixture
from sqlbuild.executor.scenario.models import (
    ScenarioCleanupExecutionResult,
    ScenarioFixtureExecutionResult,
)
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.integrations.duckdb.client import DuckDbAdapter
from sqlbuild.spec.models.schema import default_seed_csv_settings
from tests.integration.src.sqlbuild.executor.scenario._test_types import (
    ScenarioCleanupIntegrationTestCase,
    ScenarioFixtureFailureIntegrationTestCase,
    ScenarioFixtureMaterializationIntegrationTestCase,
    ScenarioProjectSeedLoadIntegrationTestCase,
)
from tests.integration.src.sqlbuild.executor.scenario.helpers import (
    SCENARIO_NAME,
    build_duckdb_cleanup_plan,
    build_duckdb_fixture_plans,
    build_duckdb_invalid_fixture_plan,
    create_table,
    relation_exists,
    relation_rows,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioFixtureMaterializationIntegrationTestCase(
            description="materializes source ref and seed fixtures in duckdb",
            expected_statuses=(
                ExecutionStatus.SUCCESS,
                ExecutionStatus.SUCCESS,
                ExecutionStatus.SUCCESS,
            ),
            expected_rows_by_relation={
                "__sqb_51b385aebe20__source__raw__orders": ((1, 10, "US"),),
                "__sqb_51b385aebe20__ref__stg_customers": ((10, "Ada"),),
                "__sqb_51b385aebe20__seed__country_codes": (("US", "United States"),),
            },
        )
    ],
    ids=["materializes source ref and seed fixtures in duckdb"],
)
def test_given_scenario_fixture_plans_when_executing_then_materializes_fixture_tables(
    test_case: ScenarioFixtureMaterializationIntegrationTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    results: tuple[ScenarioFixtureExecutionResult, ...] = execute_scenario_fixtures(
        scenario_name=SCENARIO_NAME,
        fixture_plans=build_duckdb_fixture_plans(),
        adapter=adapter,
        connection=connection,
    )

    assert tuple(result.status for result in results) == test_case.expected_statuses
    for relation_name, expected_rows in test_case.expected_rows_by_relation.items():
        assert relation_rows(connection, relation_name) == expected_rows


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioCleanupIntegrationTestCase(
            description="drops planned relations and leaves unrelated prefix relation",
            expected_status=ExecutionStatus.SUCCESS,
            planned_relation_names=(
                "__sqb_51b385aebe20__source__raw__orders",
                "__sqb_51b385aebe20__ref__stg_customers",
                "__sqb_51b385aebe20__seed__country_codes",
                "__sqb_51b385aebe20__model__daily_revenue",
            ),
            retained_relation_name="__sqb_51b385aebe20__model__stale_not_in_plan",
        )
    ],
    ids=["drops planned relations and leaves unrelated prefix relation"],
)
def test_given_scenario_plan_when_cleaning_up_then_drops_only_planned_relations(
    test_case: ScenarioCleanupIntegrationTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    scenario_plan: ScenarioExecutionPlan = build_duckdb_cleanup_plan()
    execute_scenario_fixtures(
        scenario_name=SCENARIO_NAME,
        fixture_plans=scenario_plan.fixture_plans,
        adapter=adapter,
        connection=connection,
    )
    create_table(connection, "__sqb_51b385aebe20__model__daily_revenue")
    create_table(connection, test_case.retained_relation_name)

    result: ScenarioCleanupExecutionResult = execute_scenario_cleanup(
        scenario_plan=scenario_plan,
        adapter=adapter,
        connection=connection,
    )

    assert result.status == test_case.expected_status
    for relation_name in test_case.planned_relation_names:
        assert not relation_exists(connection, relation_name)
    assert relation_exists(connection, test_case.retained_relation_name)


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioFixtureFailureIntegrationTestCase(
            description="returns failed result for invalid fixture SQL",
            expected_status=ExecutionStatus.FAILED,
            expected_error_fragment="missing_relation",
            expected_log_fragment="revenue__customer_refund:source:raw__orders",
        )
    ],
    ids=["returns failed result for invalid fixture SQL"],
)
def test_given_fixture_materialization_failure_when_executing_then_returns_failed_result(
    test_case: ScenarioFixtureFailureIntegrationTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    fixture_plan: ScenarioFixturePlan = build_duckdb_invalid_fixture_plan()

    result: ScenarioFixtureExecutionResult = execute_scenario_fixture(
        scenario_name=SCENARIO_NAME,
        fixture_plan=fixture_plan,
        adapter=adapter,
        connection=connection,
    )

    assert result.status == test_case.expected_status
    assert result.error_message is not None
    assert test_case.expected_error_fragment in result.error_message
    assert test_case.expected_log_fragment in result.lifecycle_events[-1].content


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioProjectSeedLoadIntegrationTestCase(
            description="loads required unmocked project seed into scenario target",
            expected_statuses=(ExecutionStatus.SUCCESS,),
            expected_rows=(("US", "United States"),),
        )
    ],
    ids=["loads required unmocked project seed into scenario target"],
)
def test_given_required_unmocked_seed_when_executing_then_loads_project_seed_to_scenario_target(
    test_case: ScenarioProjectSeedLoadIntegrationTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
    tmp_path: Path,
) -> None:
    seed_file: Path = tmp_path / "country_codes.csv"
    seed_file.write_text("country_code,country_name\nUS,United States\n", encoding="utf-8")
    seed_entry: SeedPlanEntry = SeedPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.SEED, name="country_codes"),
        name="country_codes",
        target=CompiledRelationTarget(
            database=None,
            schema="scenario_schema",
            name="__sqb_51b385aebe20__seed__country_codes",
            qualified_name="scenario_schema.__sqb_51b385aebe20__seed__country_codes",
        ),
        file_path=seed_file,
        columns=(
            ColumnInfo(name="country_code", type="VARCHAR"),
            ColumnInfo(name="country_name", type="VARCHAR"),
        ),
        csv_settings=default_seed_csv_settings,
    )

    results: tuple[SeedExecutionResult, ...] = execute_scenario_seed_entries(
        seed_entries=(seed_entry,),
        adapter=adapter,
        connection=connection,
    )

    assert tuple(result.status for result in results) == test_case.expected_statuses
    assert (
        relation_rows(connection, "__sqb_51b385aebe20__seed__country_codes")
        == test_case.expected_rows
    )
