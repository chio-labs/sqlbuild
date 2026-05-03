from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.compiler.planner.main import build_execution_plan
from sqlbuild.compiler.planner.models import ModelPlanEntry, PlanOutput
from sqlbuild.compiler.planner.types import PlanAction, PlanReason
from sqlbuild.integrations.duckdb.client import DuckDbAdapter
from tests.integration.src.sqlbuild.compiler.planner.main._test_types import (
    BuildExecutionPlanTestCase,
)
from tests.integration.src.sqlbuild.compiler.planner.main.helpers import (
    build_project_from_test_case,
)

BUILD_PLAN_TEST_CASES: list[BuildExecutionPlanTestCase] = [
    BuildExecutionPlanTestCase(
        description="first run table model produces create_table action",
        setup_sql=(),
        model_targets={"orders": "staging"},
        model_configs={"orders": {"materialized": "table"}},
        model_queries={"orders": "SELECT 1 AS id"},
        full_refresh=False,
        expected_action={"orders": PlanAction.CREATE_TABLE},
        expected_reason={"orders": PlanReason.FIRST_RUN},
        expected_ddl_fragments={"orders": "CREATE TABLE staging.orders AS"},
    ),
    BuildExecutionPlanTestCase(
        description="existing table with no change skips",
        setup_sql=("CREATE TABLE staging.orders AS SELECT 1 AS id",),
        model_targets={"orders": "staging"},
        model_configs={"orders": {"materialized": "table"}},
        model_queries={"orders": "SELECT 1 AS id"},
        full_refresh=False,
        expected_action={"orders": PlanAction.SKIP},
        expected_reason={"orders": PlanReason.NO_CHANGE},
    ),
    BuildExecutionPlanTestCase(
        description="full refresh forces create_table on existing table",
        setup_sql=("CREATE TABLE staging.orders AS SELECT 1 AS id",),
        model_targets={"orders": "staging"},
        model_configs={"orders": {"materialized": "table"}},
        model_queries={"orders": "SELECT 1 AS id"},
        full_refresh=True,
        expected_action={"orders": PlanAction.CREATE_TABLE},
        expected_reason={"orders": PlanReason.FULL_REFRESH},
        expected_ddl_fragments={"orders": "CREATE TABLE staging.orders AS"},
    ),
    BuildExecutionPlanTestCase(
        description="view model produces create_view action",
        setup_sql=(),
        model_targets={"orders_view": "staging"},
        model_configs={"orders_view": {"materialized": "view"}},
        model_queries={"orders_view": "SELECT 1 AS id"},
        full_refresh=False,
        expected_action={"orders_view": PlanAction.CREATE_VIEW},
        expected_reason={"orders_view": PlanReason.FIRST_RUN},
        expected_ddl_fragments={"orders_view": "CREATE OR REPLACE VIEW staging.orders_view AS"},
    ),
    BuildExecutionPlanTestCase(
        description="multiple models planned in correct order",
        setup_sql=(),
        model_targets={
            "stg_orders": "staging",
            "fact_orders": "staging",
        },
        model_configs={
            "stg_orders": {"materialized": "view"},
            "fact_orders": {"materialized": "table"},
        },
        model_queries={
            "stg_orders": "SELECT 1 AS id",
            "fact_orders": "SELECT 1 AS id",
        },
        full_refresh=False,
        expected_action={
            "stg_orders": PlanAction.CREATE_VIEW,
            "fact_orders": PlanAction.CREATE_TABLE,
        },
        expected_reason={
            "stg_orders": PlanReason.FIRST_RUN,
            "fact_orders": PlanReason.FIRST_RUN,
        },
    ),
    BuildExecutionPlanTestCase(
        description="seed appears in plan output seed entries",
        setup_sql=(),
        model_targets={"orders": "staging"},
        model_configs={"orders": {"materialized": "table"}},
        model_queries={"orders": "SELECT 1 AS id"},
        seed_targets={"country_codes": "staging"},
        full_refresh=False,
        expected_action={"orders": PlanAction.CREATE_TABLE},
        expected_reason={"orders": PlanReason.FIRST_RUN},
        expected_seed_names=("country_codes",),
    ),
    BuildExecutionPlanTestCase(
        description="select filters plan to selected models only",
        setup_sql=(),
        model_targets={
            "stg_orders": "staging",
            "fact_orders": "staging",
        },
        model_configs={
            "stg_orders": {"materialized": "view"},
            "fact_orders": {"materialized": "table"},
        },
        model_queries={
            "stg_orders": "SELECT 1 AS id",
            "fact_orders": "SELECT 1 AS id",
        },
        full_refresh=False,
        select=("stg_orders",),
        expected_action={"stg_orders": PlanAction.CREATE_VIEW},
        expected_reason={"stg_orders": PlanReason.FIRST_RUN},
        expected_model_count=1,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    BUILD_PLAN_TEST_CASES,
    ids=[case.description for case in BUILD_PLAN_TEST_CASES],
)
def test_given_project_when_building_plan_then_produces_expected_output(
    test_case: BuildExecutionPlanTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    sql: str
    for sql in test_case.setup_sql:
        connection.execute(sql)

    project: Any = build_project_from_test_case(test_case)

    plan: PlanOutput = build_execution_plan(
        project=project,
        adapter=adapter,
        connection=connection,
        full_refresh=test_case.full_refresh,
        select=test_case.select,
    )

    entry_map: dict[str, ModelPlanEntry] = {e.name: e for e in plan.model_entries}

    model_name: str
    expected_action: PlanAction
    for model_name, expected_action in test_case.expected_action.items():
        assert entry_map[model_name].action == expected_action

    expected_reason: PlanReason
    for model_name, expected_reason in test_case.expected_reason.items():
        assert entry_map[model_name].reason == expected_reason

    expected_fragment: str
    for model_name, expected_fragment in test_case.expected_ddl_fragments.items():
        assert expected_fragment in entry_map[model_name].logical_ddl

    seed_names: tuple[str, ...] = tuple(e.name for e in plan.seed_entries)
    expected_seed_name: str
    for expected_seed_name in test_case.expected_seed_names:
        assert expected_seed_name in seed_names

    expected_count: int = test_case.expected_model_count or len(test_case.expected_action)
    assert len(plan.model_entries) == expected_count
