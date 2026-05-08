from __future__ import annotations

import pytest

from sqlbuild.compiler.planner.helpers.scenario_relations import (
    build_scenario_relation_plan,
    resolve_scenario_check_sql,
)
from sqlbuild.compiler.planner.models import (
    ScenarioGraphPlan,
    ScenarioRelationPlan,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
    ScenarioCheckSqlResolutionTestCase,
    ScenarioRelationPlanErrorTestCase,
    ScenarioRelationPlanTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers.helpers import (
    build_scenario_relation_test_map,
    build_scenario_relation_test_project,
)

HASH_PREFIX: str = "51b385aebe20"
SCENARIO_NAME: str = "revenue__customer_refund"


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioRelationPlanTestCase(
            description="builds scenario relation targets for source ref seed and model artifacts",
            graph_plan=ScenarioGraphPlan(
                key=build_scenario_relation_test_project().models[0].key,
                name=SCENARIO_NAME,
                target_model_names=("daily_revenue",),
                model_names=("daily_revenue",),
                source_fixture_names=("raw__orders",),
                ref_fixture_names=("stg_customers",),
                seed_fixture_names=("country_codes",),
            ),
            expected_model_target_names={
                "daily_revenue": "scenario_schema.__sqb_51b385aebe20__model__daily_revenue",
                "stg_customers": "scenario_schema.__sqb_51b385aebe20__ref__stg_customers",
            },
            expected_seed_target_names={
                "country_codes": "scenario_schema.__sqb_51b385aebe20__seed__country_codes",
            },
            expected_source_expressions={
                "raw__orders": "scenario_schema.__sqb_51b385aebe20__source__raw__orders",
            },
        )
    ],
    ids=["builds scenario relation targets for source ref seed and model artifacts"],
)
def test_given_scenario_graph_when_building_relation_plan_then_returns_scenario_targets(
    test_case: ScenarioRelationPlanTestCase,
) -> None:
    result: ScenarioRelationPlan = build_scenario_relation_plan(
        project=build_scenario_relation_test_project(),
        graph_plan=test_case.graph_plan,
        relation_map=build_scenario_relation_test_map(),
        schema="scenario_schema",
    )

    assert {
        name: target.qualified_name for name, target in result.model_targets.items()
    } == test_case.expected_model_target_names
    assert {
        name: target.qualified_name for name, target in result.seed_targets.items()
    } == test_case.expected_seed_target_names
    assert {
        name: source.expression for name, source in result.source_map.items()
    } == test_case.expected_source_expressions


CHECK_SQL_TEST_CASES: list[ScenarioCheckSqlResolutionTestCase] = [
    ScenarioCheckSqlResolutionTestCase(
        description="resolves assertion refs to scenario model and ref fixture relations",
        sql=(
            "SELECT * FROM __ref(daily_revenue) dr "
            "JOIN __ref(stg_customers) sc ON dr.customer_id = sc.customer_id"
        ),
        expected_sql=(
            "SELECT * FROM scenario_schema.__sqb_51b385aebe20__model__daily_revenue AS dr "
            "JOIN scenario_schema.__sqb_51b385aebe20__ref__stg_customers AS sc "
            "ON dr.customer_id = sc.customer_id"
        ),
    ),
    ScenarioCheckSqlResolutionTestCase(
        description="resolves seed and source markers to scenario fixture relations",
        sql=(
            "SELECT * FROM __seed(country_codes) c "
            "JOIN __source(raw__orders) o ON c.country_code = o.country_code"
        ),
        expected_sql=(
            "SELECT * FROM scenario_schema.__sqb_51b385aebe20__seed__country_codes AS c "
            "JOIN scenario_schema.__sqb_51b385aebe20__source__raw__orders AS o "
            "ON c.country_code = o.country_code"
        ),
    ),
    ScenarioCheckSqlResolutionTestCase(
        description="sqlglot check sql resolution ignores strings and comments",
        sql=(
            "SELECT '__ref(daily_revenue)' AS marker_text "
            "FROM __ref(daily_revenue) dr -- __source(raw__orders)"
        ),
        expected_sql=(
            "SELECT '__ref(daily_revenue)' AS marker_text "
            "FROM scenario_schema.__sqb_51b385aebe20__model__daily_revenue AS dr "
            "/* __source(raw__orders) */"
        ),
    ),
    ScenarioCheckSqlResolutionTestCase(
        description="regex fallback resolves markers when sqlglot is disabled",
        sql=(
            "SELECT * FROM __seed(country_codes) c "
            "JOIN __source(raw__orders) o ON c.country_code = o.country_code"
        ),
        expected_sql=(
            "SELECT * FROM scenario_schema.__sqb_51b385aebe20__seed__country_codes c "
            "JOIN scenario_schema.__sqb_51b385aebe20__source__raw__orders o "
            "ON c.country_code = o.country_code"
        ),
        sqlglot_enabled=False,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    CHECK_SQL_TEST_CASES,
    ids=[case.description for case in CHECK_SQL_TEST_CASES],
)
def test_given_scenario_check_sql_when_resolving_then_uses_scenario_relations(
    test_case: ScenarioCheckSqlResolutionTestCase,
) -> None:
    relation_plan: ScenarioRelationPlan = build_scenario_relation_plan(
        project=build_scenario_relation_test_project(),
        graph_plan=ScenarioGraphPlan(
            key=build_scenario_relation_test_project().models[0].key,
            name=SCENARIO_NAME,
            target_model_names=("daily_revenue",),
            model_names=("daily_revenue",),
            source_fixture_names=("raw__orders",),
            ref_fixture_names=("stg_customers",),
            seed_fixture_names=("country_codes",),
        ),
        relation_map=build_scenario_relation_test_map(),
        schema="scenario_schema",
    )

    result: str = resolve_scenario_check_sql(
        sql=test_case.sql,
        relation_plan=relation_plan,
        sqlglot_enabled=test_case.sqlglot_enabled,
        sqlglot_dialect=test_case.sqlglot_dialect,
    )

    assert result == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioRelationPlanErrorTestCase(
            description="raises when relation map is missing required artifact",
            graph_plan=ScenarioGraphPlan(
                key=build_scenario_relation_test_project().models[0].key,
                name=SCENARIO_NAME,
                target_model_names=("daily_revenue",),
                model_names=("daily_revenue", "missing_model"),
            ),
            expected_error_fragment="missing model artifact 'missing_model'",
        )
    ],
    ids=["raises when relation map is missing required artifact"],
)
def test_given_missing_scenario_artifact_when_building_relation_plan_then_raises(
    test_case: ScenarioRelationPlanErrorTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        build_scenario_relation_plan(
            project=build_scenario_relation_test_project(),
            graph_plan=test_case.graph_plan,
            relation_map=build_scenario_relation_test_map(),
            schema="scenario_schema",
        )


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioCheckSqlResolutionTestCase(
            description="raises on sqlglot parse failure without regex fallback",
            sql="SELECT * FROM __ref(daily_revenue) WHERE (",
            expected_sql="could not be parsed with SQLGlot",
        )
    ],
    ids=["raises on sqlglot parse failure without regex fallback"],
)
def test_given_invalid_check_sql_when_sqlglot_enabled_then_raises_without_regex_fallback(
    test_case: ScenarioCheckSqlResolutionTestCase,
) -> None:
    relation_plan: ScenarioRelationPlan = build_scenario_relation_plan(
        project=build_scenario_relation_test_project(),
        graph_plan=ScenarioGraphPlan(
            key=build_scenario_relation_test_project().models[0].key,
            name=SCENARIO_NAME,
            target_model_names=("daily_revenue",),
            model_names=("daily_revenue",),
        ),
        relation_map=build_scenario_relation_test_map(),
        schema="scenario_schema",
    )

    with pytest.raises(ValueError, match=test_case.expected_sql):
        resolve_scenario_check_sql(
            sql=test_case.sql,
            relation_plan=relation_plan,
            sqlglot_enabled=True,
        )
