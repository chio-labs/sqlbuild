from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from pathlib import Path

import pytest

from sqlbuild.compiler.compile.models import (
    CompiledProject,
    CompiledSqlScenario,
    CompileSqlScenarioCte,
)
from sqlbuild.compiler.discovery.models import DiscoveredHookFunction
from sqlbuild.compiler.planner._helpers.scenario.relations import (
    build_scenario_execution_plan,
    build_scenario_fixture_plans,
    build_scenario_relation_plan,
    resolve_scenario_check_sql,
)
from sqlbuild.compiler.planner.models import (
    ScenarioExecutionPlan,
    ScenarioFixturePlan,
    ScenarioGraphPlan,
    ScenarioRelationPlan,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers._test_types import (
    ScenarioCheckSqlResolutionTestCase,
    ScenarioExecutionPlanTestCase,
    ScenarioFixturePlanTestCase,
    ScenarioRelationPlanErrorTestCase,
    ScenarioRelationPlanTestCase,
    ScenarioUnmockedSeedExecutionPlanTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers.helpers import (
    PlannerTestAdapter,
    build_compiled_function,
    build_scenario_relation_test_map,
    build_scenario_relation_test_project,
    build_scenario_relation_test_project_with_unused_seed,
    build_scenario_relation_test_scenario,
    quoting_render_qualified_name,
)

HASH_PREFIX: str = "51b385aebe20"
SCENARIO_NAME: str = "revenue__customer_refund"


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioRelationPlanTestCase(
            description="builds scenario relation locations for fixtures and models",
            graph_plan=ScenarioGraphPlan(
                key=build_scenario_relation_test_project().models[0].key,
                name=SCENARIO_NAME,
                target_model_names=("daily_revenue",),
                model_names=("daily_revenue",),
                source_fixture_names=("raw__orders",),
                ref_fixture_names=("stg_customers",),
                dbt_ref_fixture_names=("stripe__payments",),
                seed_names=("country_codes",),
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
                "raw__orders": None,
            },
            expected_dbt_ref_target_names={
                "stripe__payments": "scenario_schema.__sqb_51b385aebe20__dbt_ref__stripe__payments",
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_scenario_graph_when_building_relation_plan_then_returns_scenario_targets(
    test_case: ScenarioRelationPlanTestCase,
) -> None:
    result: ScenarioRelationPlan = build_scenario_relation_plan(
        project=build_scenario_relation_test_project(),
        graph_plan=test_case.graph_plan,
        relation_map=build_scenario_relation_test_map(),
        render_qualified_name=PlannerTestAdapter().render_qualified_name,
        schema="scenario_schema",
    )

    assert {
        name: target.qualified_name for name, target in result.model_locations.items()
    } == test_case.expected_model_target_names
    assert {
        name: target.qualified_name for name, target in result.seed_locations.items()
    } == test_case.expected_seed_target_names
    assert {
        name: source.expression for name, source in result.source_map.items()
    } == test_case.expected_source_expressions
    assert {
        name: target.qualified_name for name, target in result.dbt_ref_fixture_locations.items()
    } == test_case.expected_dbt_ref_target_names


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioRelationPlanTestCase(
            description="renders scenario relation names through the adapter renderer",
            graph_plan=ScenarioGraphPlan(
                key=build_scenario_relation_test_project().models[0].key,
                name=SCENARIO_NAME,
                target_model_names=("daily_revenue",),
                model_names=("daily_revenue",),
                seed_names=("country_codes",),
            ),
            expected_model_target_names={
                "daily_revenue": '"scenario_schema"."__sqb_51b385aebe20__model__daily_revenue"',
            },
            expected_seed_target_names={
                "country_codes": '"scenario_schema"."__sqb_51b385aebe20__seed__country_codes"',
            },
            expected_source_expressions={},
        )
    ],
    ids=lambda case: case.description,
)
def test_given_quoting_renderer_when_building_relation_plan_then_renders_through_adapter(
    test_case: ScenarioRelationPlanTestCase,
) -> None:
    result: ScenarioRelationPlan = build_scenario_relation_plan(
        project=build_scenario_relation_test_project(),
        graph_plan=test_case.graph_plan,
        relation_map=build_scenario_relation_test_map(),
        render_qualified_name=quoting_render_qualified_name,
        schema="scenario_schema",
    )

    assert {
        name: target.qualified_name for name, target in result.model_locations.items()
    } == test_case.expected_model_target_names
    assert {
        name: target.qualified_name for name, target in result.seed_locations.items()
    } == test_case.expected_seed_target_names


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioFixturePlanTestCase(
            description="wraps fixture SQL with shared scenario helper CTEs",
            graph_plan=ScenarioGraphPlan(
                key=build_scenario_relation_test_project().models[0].key,
                name=SCENARIO_NAME,
                target_model_names=("daily_revenue",),
                model_names=("daily_revenue",),
                source_fixture_names=("raw__orders",),
                ref_fixture_names=("stg_customers",),
                dbt_ref_fixture_names=("stripe__payments",),
                seed_names=("country_codes",),
                seed_fixture_names=("country_codes",),
            ),
            expected_fixture_sql={
                "source:raw__orders": (
                    "WITH helper_orders AS (SELECT 1 AS order_id, 10 AS customer_id) "
                    "SELECT * FROM helper_orders"
                ),
                "ref:stg_customers": (
                    "WITH helper_orders AS (SELECT 1 AS order_id, 10 AS customer_id) "
                    "SELECT 10 AS customer_id"
                ),
                "dbt_ref:stripe__payments": (
                    "WITH helper_orders AS (SELECT 1 AS order_id, 10 AS customer_id) "
                    "SELECT 1 AS payment_id, 10 AS customer_id"
                ),
                "seed:country_codes": (
                    "WITH helper_orders AS (SELECT 1 AS order_id, 10 AS customer_id) "
                    "SELECT 'US' AS country_code"
                ),
            },
            expected_fixture_targets={
                "source:raw__orders": "scenario_schema.__sqb_51b385aebe20__source__raw__orders",
                "ref:stg_customers": "scenario_schema.__sqb_51b385aebe20__ref__stg_customers",
                "dbt_ref:stripe__payments": (
                    "scenario_schema.__sqb_51b385aebe20__dbt_ref__stripe__payments"
                ),
                "seed:country_codes": "scenario_schema.__sqb_51b385aebe20__seed__country_codes",
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_scenario_helpers_when_building_fixture_plans_then_fixtures_are_self_contained(
    test_case: ScenarioFixturePlanTestCase,
) -> None:
    relation_plan: ScenarioRelationPlan = build_scenario_relation_plan(
        project=build_scenario_relation_test_project(),
        graph_plan=test_case.graph_plan,
        relation_map=build_scenario_relation_test_map(),
        render_qualified_name=PlannerTestAdapter().render_qualified_name,
        schema="scenario_schema",
    )

    result: tuple[ScenarioFixturePlan, ...] = build_scenario_fixture_plans(
        scenario=build_scenario_relation_test_scenario(),
        graph_plan=test_case.graph_plan,
        relation_plan=relation_plan,
        adapter=PlannerTestAdapter(),
    )

    assert {
        f"{fixture.kind.value}:{fixture.logical_name}": fixture.sql for fixture in result
    } == test_case.expected_fixture_sql
    assert {
        f"{fixture.kind.value}:{fixture.logical_name}": fixture.destination.qualified_name
        for fixture in result
    } == test_case.expected_fixture_targets


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioFixturePlanTestCase(
            description="resolves project source refs in scenario fixture sql",
            graph_plan=ScenarioGraphPlan(
                key=build_scenario_relation_test_project().models[0].key,
                name=SCENARIO_NAME,
                target_model_names=("daily_revenue",),
                model_names=("daily_revenue",),
                source_fixture_names=("raw__orders",),
            ),
            expected_fixture_sql={
                "source:raw__orders": "SELECT * FROM public.raw__orders WHERE order_id <= 10",
            },
            expected_fixture_targets={
                "source:raw__orders": "scenario_schema.__sqb_51b385aebe20__source__raw__orders",
            },
            fixture_sql_body='SELECT * FROM __source("raw__orders") WHERE order_id <= 10',
        ),
        ScenarioFixturePlanTestCase(
            description="resolves project source refs with polyglot without changing literals",
            graph_plan=ScenarioGraphPlan(
                key=build_scenario_relation_test_project().models[0].key,
                name=SCENARIO_NAME,
                target_model_names=("daily_revenue",),
                model_names=("daily_revenue",),
                source_fixture_names=("raw__orders",),
            ),
            expected_fixture_sql={
                "source:raw__orders": (
                    "SELECT '__source(\"raw__orders\")' AS marker_text FROM public.raw__orders AS o"
                ),
            },
            expected_fixture_targets={
                "source:raw__orders": "scenario_schema.__sqb_51b385aebe20__source__raw__orders",
            },
            fixture_sql_body=(
                "SELECT '__source(\"raw__orders\")' AS marker_text "
                'FROM __source("raw__orders") o -- __source("raw__orders")'
            ),
        ),
        ScenarioFixturePlanTestCase(
            description="falls back to regex source resolution when sql_analysis is disabled",
            graph_plan=ScenarioGraphPlan(
                key=build_scenario_relation_test_project().models[0].key,
                name=SCENARIO_NAME,
                target_model_names=("daily_revenue",),
                model_names=("daily_revenue",),
                source_fixture_names=("raw__orders",),
            ),
            expected_fixture_sql={
                "source:raw__orders": "SELECT * FROM public.raw__orders WHERE order_id <= 10",
            },
            expected_fixture_targets={
                "source:raw__orders": "scenario_schema.__sqb_51b385aebe20__source__raw__orders",
            },
            fixture_sql_body='SELECT * FROM __source("raw__orders") WHERE order_id <= 10',
            sql_analysis_enabled=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_source_ref_in_scenario_fixture_when_building_fixture_plan_then_resolves(
    test_case: ScenarioFixturePlanTestCase,
) -> None:
    scenario: CompiledSqlScenario = replace(
        build_scenario_relation_test_scenario(include_seed_fixture=False),
        authored_ctes=(
            CompileSqlScenarioCte(
                name="__source__raw__orders",
                sql_body=test_case.fixture_sql_body or "SELECT 1",
            ),
        ),
        source_fixture_names=("raw__orders",),
        ref_fixture_names=(),
        dbt_ref_fixture_names=(),
        seed_fixture_names=(),
    )
    relation_plan: ScenarioRelationPlan = build_scenario_relation_plan(
        project=build_scenario_relation_test_project(),
        graph_plan=test_case.graph_plan,
        relation_map=build_scenario_relation_test_map(),
        render_qualified_name=PlannerTestAdapter().render_qualified_name,
        schema="scenario_schema",
    )

    result: tuple[ScenarioFixturePlan, ...] = build_scenario_fixture_plans(
        scenario=scenario,
        graph_plan=test_case.graph_plan,
        relation_plan=relation_plan,
        adapter=PlannerTestAdapter(),
        sql_analysis_enabled=test_case.sql_analysis_enabled,
        sql_analysis_dialect=test_case.sql_analysis_dialect,
    )

    assert {
        f"{fixture.kind.value}:{fixture.logical_name}": fixture.sql for fixture in result
    } == test_case.expected_fixture_sql
    assert {
        f"{fixture.kind.value}:{fixture.logical_name}": fixture.destination.qualified_name
        for fixture in result
    } == test_case.expected_fixture_targets


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioExecutionPlanTestCase(
            description="builds dry run scenario execution plan with scenario targets",
            graph_plan=ScenarioGraphPlan(
                key=build_scenario_relation_test_project().models[0].key,
                name=SCENARIO_NAME,
                target_model_names=("daily_revenue",),
                assertion_target_model_names=("daily_revenue",),
                model_names=("daily_revenue",),
                source_fixture_names=("raw__orders",),
                ref_fixture_names=("stg_customers",),
                dbt_ref_fixture_names=("stripe__payments",),
                seed_names=("country_codes",),
                seed_fixture_names=("country_codes",),
                function_deps=(build_compiled_function(body_sql="").key,),
            ),
            expected_model_entry_targets={
                "daily_revenue": "scenario_schema.__sqb_51b385aebe20__model__daily_revenue",
            },
            expected_model_entry_sql_fragments={
                "daily_revenue": (
                    "scenario_schema.__sqb_51b385aebe20__source__raw__orders",
                    "scenario_schema.__sqb_51b385aebe20__ref__stg_customers",
                    "scenario_schema.__sqb_51b385aebe20__seed__country_codes",
                    "scenario_schema.__sqb_51b385aebe20__dbt_ref__stripe__payments",
                ),
            },
            expected_fixture_targets={
                "source:raw__orders": "scenario_schema.__sqb_51b385aebe20__source__raw__orders",
                "ref:stg_customers": "scenario_schema.__sqb_51b385aebe20__ref__stg_customers",
                "dbt_ref:stripe__payments": (
                    "scenario_schema.__sqb_51b385aebe20__dbt_ref__stripe__payments"
                ),
                "seed:country_codes": "scenario_schema.__sqb_51b385aebe20__seed__country_codes",
            },
            expected_seed_entry_targets={},
            expected_function_entry_targets={
                "is_completed_order": "main.is_completed_order",
            },
            expected_function_entry_sql_fragments={
                "is_completed_order": (
                    "scenario_schema.__sqb_51b385aebe20__source__raw__orders",
                    "scenario_schema.__sqb_51b385aebe20__model__daily_revenue",
                ),
            },
            expected_expected_actual_destinations={
                "daily_revenue": "scenario_schema.__sqb_51b385aebe20__model__daily_revenue",
            },
            expected_expected_sql={
                "daily_revenue": (
                    "SELECT * FROM scenario_schema.__sqb_51b385aebe20__model__daily_revenue"
                ),
            },
            expected_assertion_sql={
                "no_negative_revenue": (
                    "SELECT * FROM "
                    "scenario_schema.__sqb_51b385aebe20__model__daily_revenue "
                    "WHERE revenue < 0"
                ),
            },
            expected_hook_names=("notify",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_scenario_graph_when_building_execution_plan_then_returns_scenario_plan(
    test_case: ScenarioExecutionPlanTestCase,
) -> None:
    base_project: CompiledProject = build_scenario_relation_test_project()

    def notify() -> None:
        return None

    project: CompiledProject = replace(
        base_project,
        functions=(
            build_compiled_function(
                body_sql=(
                    'EXISTS (SELECT 1 FROM __source("raw__orders")) '
                    'AND EXISTS (SELECT 1 FROM __ref("daily_revenue"))'
                )
            ),
        ),
        hook_functions=(
            DiscoveredHookFunction(
                file_path=Path(__file__),
                relative_path=Path("hooks/python/notify.py"),
                name="notify",
                function=notify,
            ),
        ),
    )
    relation_plan: ScenarioRelationPlan = build_scenario_relation_plan(
        project=project,
        graph_plan=test_case.graph_plan,
        relation_map=build_scenario_relation_test_map(),
        render_qualified_name=PlannerTestAdapter().render_qualified_name,
        schema="scenario_schema",
    )

    result, warnings = build_scenario_execution_plan(
        scenario=build_scenario_relation_test_scenario(),
        project=project,
        adapter=PlannerTestAdapter(),
        graph_plan=test_case.graph_plan,
        relation_plan=relation_plan,
    )

    assert warnings == ()
    assert isinstance(result, ScenarioExecutionPlan)
    assert {
        entry.name: entry.destination.qualified_name for entry in result.model_entries
    } == test_case.expected_model_entry_targets
    for entry in result.model_entries:
        for expected_fragment in test_case.expected_model_entry_sql_fragments[entry.name]:
            assert expected_fragment in entry.resolved_sql
    assert {
        f"{fixture.kind.value}:{fixture.logical_name}": fixture.destination.qualified_name
        for fixture in result.fixture_plans
    } == test_case.expected_fixture_targets
    assert {
        entry.name: entry.destination.qualified_name for entry in result.seed_entries
    } == test_case.expected_seed_entry_targets
    assert {
        entry.name: entry.destination.qualified_name for entry in result.function_entries
    } == test_case.expected_function_entry_targets
    for entry in result.function_entries:
        for expected_fragment in test_case.expected_function_entry_sql_fragments[entry.name]:
            assert expected_fragment in entry.body_sql
    assert {
        expectation.model_name: expectation.actual_destination.qualified_name
        for expectation in result.expected_expectations
    } == test_case.expected_expected_actual_destinations
    assert {
        expectation.model_name: expectation.expected_sql
        for expectation in result.expected_expectations
    } == test_case.expected_expected_sql
    assert {
        expectation.name: expectation.sql for expectation in result.assertion_expectations
    } == test_case.expected_assertion_sql
    assert tuple(hook.name for hook in result.hook_functions) == test_case.expected_hook_names


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioUnmockedSeedExecutionPlanTestCase(
            description="loads required unmocked seed from project seed file",
            graph_plan=ScenarioGraphPlan(
                key=build_scenario_relation_test_project().models[0].key,
                name=SCENARIO_NAME,
                target_model_names=("daily_revenue",),
                assertion_target_model_names=("daily_revenue",),
                model_names=("daily_revenue",),
                source_fixture_names=("raw__orders",),
                ref_fixture_names=("stg_customers",),
                seed_names=("country_codes",),
            ),
            project=build_scenario_relation_test_project(),
            expected_seed_fixture_names=frozenset(),
            expected_seed_entry_targets={
                "country_codes": "scenario_schema.__sqb_51b385aebe20__seed__country_codes"
            },
        ),
        ScenarioUnmockedSeedExecutionPlanTestCase(
            description="ignores project seeds outside the scenario graph",
            graph_plan=ScenarioGraphPlan(
                key=build_scenario_relation_test_project().models[0].key,
                name=SCENARIO_NAME,
                target_model_names=("daily_revenue",),
                assertion_target_model_names=("daily_revenue",),
                model_names=("daily_revenue",),
                source_fixture_names=("raw__orders",),
                ref_fixture_names=("stg_customers",),
                seed_names=("country_codes",),
            ),
            project=build_scenario_relation_test_project_with_unused_seed(),
            expected_seed_fixture_names=frozenset(),
            expected_seed_entry_targets={
                "country_codes": "scenario_schema.__sqb_51b385aebe20__seed__country_codes"
            },
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_required_unmocked_seed_when_building_execution_plan_then_loads_project_seed(
    test_case: ScenarioUnmockedSeedExecutionPlanTestCase,
) -> None:
    project: CompiledProject = test_case.project
    relation_plan: ScenarioRelationPlan = build_scenario_relation_plan(
        project=project,
        graph_plan=test_case.graph_plan,
        relation_map=build_scenario_relation_test_map(),
        render_qualified_name=PlannerTestAdapter().render_qualified_name,
        schema="scenario_schema",
    )

    result, warnings = build_scenario_execution_plan(
        scenario=build_scenario_relation_test_scenario(include_seed_fixture=False),
        project=project,
        adapter=PlannerTestAdapter(),
        graph_plan=test_case.graph_plan,
        relation_plan=relation_plan,
    )

    assert warnings == ()
    fixture_names_by_kind: defaultdict[str, set[str]] = defaultdict(set)
    for fixture in result.fixture_plans:
        fixture_names_by_kind[fixture.kind.value].add(fixture.logical_name)
    assert fixture_names_by_kind["seed"] == test_case.expected_seed_fixture_names
    assert {
        entry.name: entry.destination.qualified_name for entry in result.seed_entries
    } == test_case.expected_seed_entry_targets


@pytest.mark.parametrize(
    "test_case",
    [
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
            description="resolves dbt ref markers to scenario fixture relations",
            sql='SELECT * FROM __dbt_ref("stripe", "payments") p',
            expected_sql=(
                "SELECT * FROM scenario_schema.__sqb_51b385aebe20__dbt_ref__stripe__payments AS p"
            ),
        ),
        ScenarioCheckSqlResolutionTestCase(
            description="polyglot check sql resolution ignores strings and comments",
            sql=(
                "SELECT '__ref(daily_revenue)' AS marker_text "
                "FROM __ref(daily_revenue) dr -- __source(raw__orders)"
            ),
            expected_sql=(
                "SELECT '__ref(daily_revenue)' AS marker_text "
                "FROM scenario_schema.__sqb_51b385aebe20__model__daily_revenue AS dr"
            ),
        ),
        ScenarioCheckSqlResolutionTestCase(
            description="regex fallback resolves markers when sql_analysis is disabled",
            sql=(
                "SELECT * FROM __seed(country_codes) c "
                "JOIN __source(raw__orders) o ON c.country_code = o.country_code"
            ),
            expected_sql=(
                "SELECT * FROM scenario_schema.__sqb_51b385aebe20__seed__country_codes c "
                "JOIN scenario_schema.__sqb_51b385aebe20__source__raw__orders o "
                "ON c.country_code = o.country_code"
            ),
            sql_analysis_enabled=False,
        ),
    ],
    ids=lambda case: case.description,
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
            dbt_ref_fixture_names=("stripe__payments",),
            seed_names=("country_codes",),
            seed_fixture_names=("country_codes",),
        ),
        relation_map=build_scenario_relation_test_map(),
        render_qualified_name=PlannerTestAdapter().render_qualified_name,
        schema="scenario_schema",
    )

    result: str = resolve_scenario_check_sql(
        sql=test_case.sql,
        relation_plan=relation_plan,
        adapter=PlannerTestAdapter(),
        sql_analysis_enabled=test_case.sql_analysis_enabled,
        sql_analysis_dialect=test_case.sql_analysis_dialect,
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
    ids=lambda case: case.description,
)
def test_given_missing_scenario_artifact_when_building_relation_plan_then_raises(
    test_case: ScenarioRelationPlanErrorTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        build_scenario_relation_plan(
            project=build_scenario_relation_test_project(),
            graph_plan=test_case.graph_plan,
            relation_map=build_scenario_relation_test_map(),
            render_qualified_name=PlannerTestAdapter().render_qualified_name,
            schema="scenario_schema",
        )


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioCheckSqlResolutionTestCase(
            description="raises on polyglot parse failure without regex fallback",
            sql="SELECT * FROM __ref(daily_revenue) WHERE (",
            expected_sql="could not be parsed with Polyglot",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_check_sql_when_sql_analysis_enabled_then_raises_without_regex_fallback(
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
        render_qualified_name=PlannerTestAdapter().render_qualified_name,
        schema="scenario_schema",
    )

    with pytest.raises(ValueError, match=test_case.expected_sql):
        resolve_scenario_check_sql(
            sql=test_case.sql,
            relation_plan=relation_plan,
            adapter=PlannerTestAdapter(),
            sql_analysis_enabled=True,
        )
