from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledSqlScenario,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.helpers.scenario.graph import plan_scenario_graph
from sqlbuild.compiler.planner.models import ScenarioGraphPlan
from sqlbuild.compiler.planner.types import WarningSeverity
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
    PlanScenarioGraphErrorTestCase,
    PlanScenarioGraphTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers.helpers import (
    build_scenario_from_test_case,
    build_test_project,
)

SCENARIO_KEY: CompiledObjectKey = CompiledObjectKey(
    resource_type=CompiledResourceType.SQL_SCENARIO,
    name="revenue__customer_refund",
)


@pytest.mark.parametrize(
    "test_case",
    [
        PlanScenarioGraphTestCase(
            description="expected cte infers target and upstream closure",
            model_deps={
                "stg_orders": ("raw__orders",),
                "daily_revenue": ("stg_orders",),
            },
            source_names=("raw__orders",),
            seed_names=(),
            expected_model_names=("daily_revenue",),
            source_fixture_names=("raw__orders",),
            expected_plan=ScenarioGraphPlan(
                key=SCENARIO_KEY,
                name="revenue__customer_refund",
                target_model_names=("daily_revenue",),
                model_names=("daily_revenue", "stg_orders"),
                source_fixture_names=("raw__orders",),
            ),
        ),
        PlanScenarioGraphTestCase(
            description="assertion refs infer targets",
            model_deps={"daily_revenue": ("raw__orders",)},
            source_names=("raw__orders",),
            seed_names=(),
            assertion_sql_bodies=("SELECT * FROM __ref(daily_revenue) WHERE revenue < 0",),
            source_fixture_names=("raw__orders",),
            expected_plan=ScenarioGraphPlan(
                key=SCENARIO_KEY,
                name="revenue__customer_refund",
                target_model_names=("daily_revenue",),
                assertion_target_model_names=("daily_revenue",),
                model_names=("daily_revenue",),
                source_fixture_names=("raw__orders",),
            ),
        ),
        PlanScenarioGraphTestCase(
            description="sql_analysis assertion target inference ignores strings and comments",
            model_deps={"daily_revenue": ("raw__orders",)},
            source_names=("raw__orders",),
            seed_names=(),
            assertion_sql_bodies=(
                "SELECT '__ref(not_a_model)' AS marker_text "
                "FROM __ref(daily_revenue) -- __ref(commented_model)",
            ),
            source_fixture_names=("raw__orders",),
            expected_plan=ScenarioGraphPlan(
                key=SCENARIO_KEY,
                name="revenue__customer_refund",
                target_model_names=("daily_revenue",),
                assertion_target_model_names=("daily_revenue",),
                model_names=("daily_revenue",),
                source_fixture_names=("raw__orders",),
            ),
        ),
        PlanScenarioGraphTestCase(
            description="mixed expected and assertion targets are unioned",
            model_deps={
                "daily_revenue": ("raw__orders",),
                "customer_revenue": ("raw__orders",),
            },
            source_names=("raw__orders",),
            seed_names=(),
            expected_model_names=("daily_revenue",),
            assertion_sql_bodies=("SELECT * FROM __ref(customer_revenue)",),
            source_fixture_names=("raw__orders",),
            expected_plan=ScenarioGraphPlan(
                key=SCENARIO_KEY,
                name="revenue__customer_refund",
                target_model_names=("customer_revenue", "daily_revenue"),
                assertion_target_model_names=("customer_revenue",),
                model_names=("customer_revenue", "daily_revenue"),
                source_fixture_names=("raw__orders",),
            ),
        ),
        PlanScenarioGraphTestCase(
            description="ref fixture boundary stops traversal",
            model_deps={
                "stg_orders": ("raw__orders",),
                "daily_revenue": ("stg_orders",),
            },
            source_names=("raw__orders",),
            seed_names=(),
            expected_model_names=("daily_revenue",),
            ref_fixture_names=("stg_orders",),
            expected_plan=ScenarioGraphPlan(
                key=SCENARIO_KEY,
                name="revenue__customer_refund",
                target_model_names=("daily_revenue",),
                model_names=("daily_revenue",),
                ref_fixture_names=("stg_orders",),
            ),
        ),
        PlanScenarioGraphTestCase(
            description="required seed is included without explicit fixture",
            model_deps={"daily_revenue": ("country_codes",)},
            source_names=(),
            seed_names=("country_codes",),
            expected_model_names=("daily_revenue",),
            expected_plan=ScenarioGraphPlan(
                key=SCENARIO_KEY,
                name="revenue__customer_refund",
                target_model_names=("daily_revenue",),
                model_names=("daily_revenue",),
                seed_names=("country_codes",),
            ),
        ),
        PlanScenarioGraphTestCase(
            description="explicit seed fixture overrides required seed",
            model_deps={"daily_revenue": ("country_codes",)},
            source_names=(),
            seed_names=("country_codes",),
            expected_model_names=("daily_revenue",),
            seed_fixture_names=("country_codes",),
            expected_plan=ScenarioGraphPlan(
                key=SCENARIO_KEY,
                name="revenue__customer_refund",
                target_model_names=("daily_revenue",),
                model_names=("daily_revenue",),
                seed_names=("country_codes",),
                seed_fixture_names=("country_codes",),
            ),
        ),
        PlanScenarioGraphTestCase(
            description="dbt ref fixture boundary stops traversal at dbt-owned relation",
            model_deps={"daily_revenue": ("stripe.payments",)},
            source_names=(),
            seed_names=(),
            expected_model_names=("daily_revenue",),
            dbt_ref_fixture_names=("stripe__payments",),
            expected_plan=ScenarioGraphPlan(
                key=SCENARIO_KEY,
                name="revenue__customer_refund",
                target_model_names=("daily_revenue",),
                model_names=("daily_revenue",),
                dbt_ref_fixture_names=("stripe__payments",),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_scenario_when_planning_graph_then_infers_expected_slice(
    test_case: PlanScenarioGraphTestCase,
) -> None:
    scenario: CompiledSqlScenario = build_scenario_from_test_case(test_case)

    result, warnings = plan_scenario_graph(
        scenario=scenario,
        project=build_test_project(
            model_deps=test_case.model_deps,
            source_names=test_case.source_names,
            seed_names=test_case.seed_names,
            dbt_ref_names=("stripe.payments",),
        ),
    )

    assert warnings == ()
    assert result == test_case.expected_plan


@pytest.mark.parametrize(
    "test_case",
    [
        PlanScenarioGraphErrorTestCase(
            description="missing source fixture fails clearly",
            model_deps={"daily_revenue": ("raw__orders",)},
            source_names=("raw__orders",),
            seed_names=(),
            expected_model_names=("daily_revenue",),
            expected_error_fragment="requires source 'raw__orders'",
        ),
        PlanScenarioGraphErrorTestCase(
            description="unknown expected target fails clearly",
            model_deps={},
            source_names=(),
            seed_names=(),
            expected_model_names=("daily_revenue",),
            expected_error_fragment="expects unknown model 'daily_revenue'",
        ),
        PlanScenarioGraphErrorTestCase(
            description="unknown assertion ref fails clearly",
            model_deps={},
            source_names=(),
            seed_names=(),
            assertion_sql_bodies=("SELECT * FROM __ref(daily_revenue)",),
            expected_error_fragment="assertion references unknown model 'daily_revenue'",
        ),
        PlanScenarioGraphErrorTestCase(
            description="polyglot assertion parse failure fails clearly without regex fallback",
            model_deps={"daily_revenue": ()},
            source_names=(),
            seed_names=(),
            assertion_sql_bodies=("SELECT * FROM __ref(daily_revenue) WHERE (",),
            expected_error_fragment="could not be parsed with Polyglot",
        ),
        PlanScenarioGraphErrorTestCase(
            description="unknown ref fixture fails clearly",
            model_deps={"daily_revenue": ()},
            source_names=(),
            seed_names=(),
            expected_model_names=("daily_revenue",),
            ref_fixture_names=("missing_model",),
            expected_error_fragment="fixture for unknown model 'missing_model'",
        ),
        PlanScenarioGraphErrorTestCase(
            description="unknown source fixture fails clearly",
            model_deps={"daily_revenue": ()},
            source_names=(),
            seed_names=(),
            expected_model_names=("daily_revenue",),
            source_fixture_names=("raw__orders",),
            expected_error_fragment="fixture for unknown source 'raw__orders'",
        ),
        PlanScenarioGraphErrorTestCase(
            description="unknown seed fixture fails clearly",
            model_deps={"daily_revenue": ()},
            source_names=(),
            seed_names=(),
            expected_model_names=("daily_revenue",),
            seed_fixture_names=("country_codes",),
            expected_error_fragment="fixture for unknown seed 'country_codes'",
        ),
        PlanScenarioGraphErrorTestCase(
            description="missing dbt ref fixture fails clearly",
            model_deps={"daily_revenue": ("stripe.payments",)},
            source_names=(),
            seed_names=(),
            expected_model_names=("daily_revenue",),
            expected_error_fragment="requires dbt ref 'stripe__payments'",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_scenario_when_planning_graph_then_returns_clear_error(
    test_case: PlanScenarioGraphErrorTestCase,
) -> None:
    scenario: CompiledSqlScenario = build_scenario_from_test_case(test_case)

    _plan, warnings = plan_scenario_graph(
        scenario=scenario,
        project=build_test_project(
            model_deps=test_case.model_deps,
            source_names=test_case.source_names,
            seed_names=test_case.seed_names,
            dbt_ref_names=("stripe.payments",),
        ),
    )

    error_messages: tuple[str, ...] = tuple(
        warning.message for warning in warnings if warning.severity == WarningSeverity.ERROR
    )
    assert any(test_case.expected_error_fragment in message for message in error_messages)
