from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.cli.commands.main.plan.helpers.formatter import format_plan
from sqlbuild.compiler.planner.main import build_execution_plan
from sqlbuild.compiler.planner.models import CascadeResult, ModelPlanEntry, PlanOutput, PlanWarning
from sqlbuild.compiler.planner.types import BackfillAction, PlanAction, PlanReason, WarningSeverity
from sqlbuild.integrations.duckdb.client import DuckDbAdapter
from tests.integration.src.sqlbuild.compiler.planner.main._test_types import (
    BuildExecutionPlanTestCase,
    FormatPlanIntegrationTestCase,
)
from tests.integration.src.sqlbuild.compiler.planner.main.helpers import (
    build_project_from_format_test_case,
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
        description="existing table with no change always rebuilds",
        setup_sql=("CREATE TABLE staging.orders AS SELECT 1 AS id",),
        model_targets={"orders": "staging"},
        model_configs={"orders": {"materialized": "table"}},
        model_queries={"orders": "SELECT 1 AS id"},
        full_refresh=False,
        expected_action={"orders": PlanAction.CREATE_TABLE},
        expected_reason={"orders": PlanReason.NO_CHANGE},
        expected_ddl_fragments={"orders": "CREATE TABLE staging.orders AS"},
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


CURSOR_TYPE_MISMATCH_TEST_CASES: list[BuildExecutionPlanTestCase] = [
    BuildExecutionPlanTestCase(
        description="heuristic cursor type mismatch produces warning",
        setup_sql=("CREATE TABLE staging.events AS SELECT 1 AS event_id, 100 AS event_time",),
        model_targets={"events": "staging"},
        model_configs={
            "events": {
                "materialized": "incremental",
                "incremental_strategy": "delete_insert",
                "cursor": "event_time",
                "cursor_type": "timestamp",
                "unique_key": "event_id",
            },
        },
        model_queries={"events": "SELECT 1 AS event_id, 100 AS event_time"},
        full_refresh=False,
        expected_action={"events": PlanAction.INCREMENTAL_DELETE_INSERT},
        expected_reason={"events": PlanReason.NORMAL_INCREMENTAL},
        expected_warning_count=1,
        expected_warning_severity=WarningSeverity.WARNING,
        expected_warning_fragment="appears to be integer",
    ),
    BuildExecutionPlanTestCase(
        description="sqlglot cursor type mismatch produces error",
        setup_sql=("CREATE TABLE staging.events AS SELECT 1 AS event_id, 100 AS event_time",),
        model_targets={"events": "staging"},
        model_configs={
            "events": {
                "materialized": "incremental",
                "incremental_strategy": "delete_insert",
                "cursor": "event_time",
                "cursor_type": "timestamp",
                "unique_key": "event_id",
            },
        },
        model_queries={"events": "SELECT 1 AS event_id, 100 AS event_time"},
        full_refresh=False,
        effective_connection={"sqlglot": True},
        expected_action={"events": PlanAction.INCREMENTAL_DELETE_INSERT},
        expected_reason={"events": PlanReason.NORMAL_INCREMENTAL},
        expected_warning_count=1,
        expected_warning_severity=WarningSeverity.ERROR,
        expected_warning_fragment="which is integer",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    CURSOR_TYPE_MISMATCH_TEST_CASES,
    ids=[case.description for case in CURSOR_TYPE_MISMATCH_TEST_CASES],
)
def test_given_cursor_type_mismatch_when_building_plan_then_produces_warning(
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
    )

    entry_map: dict[str, ModelPlanEntry] = {e.name: e for e in plan.model_entries}

    model_name: str
    expected_action: PlanAction
    for model_name, expected_action in test_case.expected_action.items():
        assert entry_map[model_name].action == expected_action

    assert len(plan.warnings) == test_case.expected_warning_count
    warning: PlanWarning = plan.warnings[0]
    assert warning.severity == test_case.expected_warning_severity
    assert test_case.expected_warning_fragment is not None
    assert test_case.expected_warning_fragment in warning.message


@pytest.mark.parametrize(
    "test_case",
    [
        BuildExecutionPlanTestCase(
            description="upstream first run full cascades to existing downstream",
            setup_sql=("CREATE TABLE staging.fact_orders AS SELECT 1 AS id",),
            model_targets={
                "stg_orders": "staging",
                "fact_orders": "staging",
            },
            model_configs={
                "stg_orders": {"materialized": "table"},
                "fact_orders": {"materialized": "table"},
            },
            model_queries={
                "stg_orders": "SELECT 1 AS id",
                "fact_orders": "SELECT 1 AS id",
            },
            model_deps={"fact_orders": ("stg_orders",)},
            full_refresh=False,
            expected_action={
                "stg_orders": PlanAction.CREATE_TABLE,
                "fact_orders": PlanAction.CREATE_TABLE,
            },
            expected_reason={
                "stg_orders": PlanReason.FIRST_RUN,
                "fact_orders": PlanReason.NO_CHANGE,
            },
            expected_cascade_action={"fact_orders": BackfillAction.FULL},
            expected_cascade_root_cause={"fact_orders": "stg_orders"},
        ),
    ],
    ids=["upstream first run full cascades to existing downstream"],
)
def test_given_upstream_first_run_when_building_plan_then_cascades_to_downstream(
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
    )

    entry_map: dict[str, ModelPlanEntry] = {e.name: e for e in plan.model_entries}

    model_name: str
    expected_action: PlanAction
    for model_name, expected_action in test_case.expected_action.items():
        assert entry_map[model_name].action == expected_action

    expected_cascade_action: BackfillAction
    for model_name, expected_cascade_action in test_case.expected_cascade_action.items():
        cascade: CascadeResult | None = entry_map[model_name].cascade
        assert cascade is not None
        assert cascade.effective_action == expected_cascade_action

    expected_root: str
    for model_name, expected_root in test_case.expected_cascade_root_cause.items():
        cascade_for_root: CascadeResult | None = entry_map[model_name].cascade
        assert cascade_for_root is not None
        assert cascade_for_root.root_cause == expected_root


FORMAT_PLAN_TEST_CASES: list[FormatPlanIntegrationTestCase] = [
    FormatPlanIntegrationTestCase(
        description="new project formats with first run group and seeds",
        setup_sql=(),
        model_targets={
            "stg_orders": "staging",
            "dim_customers": "staging",
        },
        model_configs={
            "stg_orders": {"materialized": "view"},
            "dim_customers": {"materialized": "table"},
        },
        model_queries={
            "stg_orders": "SELECT 1 AS id",
            "dim_customers": "SELECT 1 AS id",
        },
        seed_targets={"country_codes": "staging"},
        full_refresh=False,
        expected_format_fragments=(
            "Plan ready (3 selected)",
            "First run (2)",
            "stg_orders",
            "view",
            "dim_customers",
            "table",
            "Seeds (1)",
            "country_codes",
        ),
        unexpected_format_fragments=("Normal", "Query changed", "Upstream changed"),
    ),
    FormatPlanIntegrationTestCase(
        description="cascade formats with upstream changed group and cause line",
        setup_sql=("CREATE TABLE staging.fact_orders AS SELECT 1 AS id",),
        model_targets={
            "stg_orders": "staging",
            "fact_orders": "staging",
        },
        model_configs={
            "stg_orders": {"materialized": "table"},
            "fact_orders": {"materialized": "table"},
        },
        model_queries={
            "stg_orders": "SELECT 1 AS id",
            "fact_orders": "SELECT 1 AS id",
        },
        model_deps={"fact_orders": ("stg_orders",)},
        full_refresh=False,
        expected_format_fragments=(
            "Plan ready",
            "First run (1)",
            "stg_orders",
            "Upstream changed (1)",
            "fact_orders",
            "full rebuild",
            "cause: stg_orders",
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    FORMAT_PLAN_TEST_CASES,
    ids=[case.description for case in FORMAT_PLAN_TEST_CASES],
)
def test_given_real_plan_when_formatting_then_contains_expected_fragments(
    test_case: FormatPlanIntegrationTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    sql: str
    for sql in test_case.setup_sql:
        connection.execute(sql)

    project: Any = build_project_from_format_test_case(test_case)

    plan: PlanOutput = build_execution_plan(
        project=project,
        adapter=adapter,
        connection=connection,
        full_refresh=test_case.full_refresh,
    )

    result: str = format_plan(plan, full_refresh=test_case.full_refresh)

    fragment: str
    for fragment in test_case.expected_format_fragments:
        assert fragment in result, f"Expected '{fragment}' in output:\n{result}"
    for fragment in test_case.unexpected_format_fragments:
        assert fragment not in result, f"Did not expect '{fragment}' in output:\n{result}"
