from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.cli.output.main.plan import format_plan
from sqlbuild.compiler.compile.types import FunctionLanguage
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import (
    CascadeResult,
    ModelPlanEntry,
    PlanOutput,
    PlanWarning,
)
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    PlanAction,
    PlanReason,
    WarningSeverity,
)
from tests.integration.src.sqlbuild.compiler.planner.main._test_types import (
    BuildExecutionPlanTestCase,
    FormatPlanIntegrationTestCase,
    SourceCursorInputPlanErrorTestCase,
)
from tests.integration.src.sqlbuild.compiler.planner.main.helpers import (
    build_execution_plan_from_kwargs,
    build_project_from_format_test_case,
    build_project_from_source_cursor_input_test_case,
    build_project_from_test_case,
    write_previous_function_fingerprints,
)


@pytest.mark.parametrize(
    "test_case",
    [
        BuildExecutionPlanTestCase(
            description="first run table model produces create_table action",
            setup_sql=(),
            model_locations={"orders": "staging"},
            model_configs={"orders": {"materialized": "table"}},
            model_queries={"orders": "SELECT 1 AS id"},
            full_refresh=False,
            expected_action={"orders": PlanAction.CREATE_TABLE},
            expected_reason={"orders": PlanReason.FIRST_RUN},
            expected_ddl_fragments={"orders": "CREATE OR REPLACE TABLE staging.orders AS"},
            expected_progress_fragments=(
                "Inspecting warehouse state...",
                "Inspected warehouse state. (",
                "Generating plan...",
                "Generated plan. (",
            ),
        ),
        BuildExecutionPlanTestCase(
            description="existing table with no change always rebuilds",
            setup_sql=("CREATE TABLE staging.orders AS SELECT 1 AS id",),
            model_locations={"orders": "staging"},
            model_configs={"orders": {"materialized": "table"}},
            model_queries={"orders": "SELECT 1 AS id"},
            full_refresh=False,
            expected_action={"orders": PlanAction.CREATE_TABLE},
            expected_reason={"orders": PlanReason.NO_CHANGE},
            expected_ddl_fragments={"orders": "CREATE OR REPLACE TABLE staging.orders AS"},
        ),
        BuildExecutionPlanTestCase(
            description="full refresh forces create_table on existing table",
            setup_sql=("CREATE TABLE staging.orders AS SELECT 1 AS id",),
            model_locations={"orders": "staging"},
            model_configs={"orders": {"materialized": "table"}},
            model_queries={"orders": "SELECT 1 AS id"},
            full_refresh=True,
            expected_action={"orders": PlanAction.CREATE_TABLE},
            expected_reason={"orders": PlanReason.FULL_REFRESH},
            expected_ddl_fragments={"orders": "CREATE OR REPLACE TABLE staging.orders AS"},
        ),
        BuildExecutionPlanTestCase(
            description="view model produces create_view action",
            setup_sql=(),
            model_locations={"orders_view": "staging"},
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
            model_locations={
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
            model_locations={"orders": "staging"},
            model_configs={"orders": {"materialized": "table"}},
            model_queries={"orders": "SELECT 1 AS id"},
            seed_locations={"country_codes": "staging"},
            full_refresh=False,
            expected_action={"orders": PlanAction.CREATE_TABLE},
            expected_reason={"orders": PlanReason.FIRST_RUN},
            expected_seed_names=("country_codes",),
        ),
        BuildExecutionPlanTestCase(
            description="select filters plan to selected models only",
            setup_sql=(),
            model_locations={
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
    ],
    ids=lambda case: case.description,
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

    progress_messages: list[str] = []
    plan: PlanOutput = build_execution_plan_from_kwargs(
        project=project,
        adapter=adapter,
        connection=connection,
        full_refresh=test_case.full_refresh,
        select=test_case.select,
        on_progress=progress_messages.append,
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

    progress_output: str = "\n".join(progress_messages)
    expected_progress_fragment: str
    for expected_progress_fragment in test_case.expected_progress_fragments:
        assert expected_progress_fragment in progress_output


@pytest.mark.parametrize(
    "test_case",
    [
        SourceCursorInputPlanErrorTestCase(
            description="source cursor input column missing from warehouse metadata",
            setup_sql=(
                "CREATE SCHEMA raw",
                "CREATE TABLE raw.orders (order_id INTEGER, event_time TIMESTAMP)",
            ),
            model_name="orders_incremental",
            source_name="raw_orders",
            source_schema="raw",
            source_table="orders",
            cursor_column="event_time",
            cursor_input_column="loaded_at",
            expected_error_fragment=(
                "model 'orders_incremental': cursor_inputs references source 'raw_orders' "
                "column 'loaded_at'"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_missing_source_cursor_input_column_when_building_plan_then_raises_planner_error(
    test_case: SourceCursorInputPlanErrorTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    sql: str
    for sql in test_case.setup_sql:
        connection.execute(sql)

    project: Any = build_project_from_source_cursor_input_test_case(test_case)

    with pytest.raises(PlannerInputError, match=test_case.expected_error_fragment):
        build_execution_plan_from_kwargs(
            project=project,
            adapter=adapter,
            connection=connection,
            full_refresh=False,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        BuildExecutionPlanTestCase(
            description="heuristic cursor type mismatch produces warning",
            setup_sql=("CREATE TABLE staging.events AS SELECT 1 AS event_id, 100 AS event_time",),
            model_locations={"events": "staging"},
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
            expected_progress_fragments=(
                "Gathering cursor bounds (1/1)",
                "Gathered cursor bounds (1/1). (",
            ),
        ),
        BuildExecutionPlanTestCase(
            description="sql_analysis cursor type mismatch produces error",
            setup_sql=("CREATE TABLE staging.events AS SELECT 1 AS event_id, 100 AS event_time",),
            model_locations={"events": "staging"},
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
            effective_connection={"sql_analysis": True},
            expected_action={"events": PlanAction.INCREMENTAL_DELETE_INSERT},
            expected_reason={"events": PlanReason.NORMAL_INCREMENTAL},
            expected_warning_count=1,
            expected_warning_severity=WarningSeverity.ERROR,
            expected_warning_fragment="which is integer",
        ),
    ],
    ids=lambda case: case.description,
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

    progress_messages: list[str] = []
    plan: PlanOutput = build_execution_plan_from_kwargs(
        project=project,
        adapter=adapter,
        connection=connection,
        full_refresh=test_case.full_refresh,
        on_progress=progress_messages.append,
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

    progress_output: str = "\n".join(progress_messages)
    expected_progress_fragment: str
    for expected_progress_fragment in test_case.expected_progress_fragments:
        assert expected_progress_fragment in progress_output


@pytest.mark.parametrize(
    "test_case",
    [
        BuildExecutionPlanTestCase(
            description="upstream first run full cascades to existing downstream",
            setup_sql=("CREATE TABLE staging.fact_orders AS SELECT 1 AS id",),
            model_locations={
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
                "fact_orders": PlanReason.FULL_REFRESH,
            },
            expected_cascade_action={"fact_orders": BackfillAction.FULL},
            expected_cascade_root_cause={"fact_orders": "stg_orders"},
        ),
        BuildExecutionPlanTestCase(
            description="upstream full cascade forces existing incremental downstream rebuild",
            setup_sql=("CREATE TABLE staging.fact_orders AS SELECT 1 AS id",),
            model_locations={
                "stg_orders": "staging",
                "fact_orders": "staging",
            },
            model_configs={
                "stg_orders": {"materialized": "table"},
                "fact_orders": {
                    "materialized": "incremental",
                    "incremental_strategy": "delete_insert",
                    "cursor": "id",
                    "cursor_type": "integer",
                    "unique_key": "id",
                },
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
                "fact_orders": PlanReason.FULL_REFRESH,
            },
            expected_ddl_fragments={
                "fact_orders": "CREATE OR REPLACE TABLE staging.fact_orders AS",
            },
            expected_cascade_action={"fact_orders": BackfillAction.FULL},
            expected_cascade_root_cause={"fact_orders": "stg_orders"},
        ),
        BuildExecutionPlanTestCase(
            description="changed SQL UDF cascades full rebuild to incremental downstream",
            setup_sql=("CREATE TABLE staging.fact_orders AS SELECT 1 AS id",),
            model_locations={"fact_orders": "staging"},
            function_locations={"is_priority_order": "staging"},
            function_bodies={"is_priority_order": "value = 2"},
            previous_function_bodies={"is_priority_order": "value = 1"},
            function_replay_on_changes={"is_priority_order": "full"},
            function_deps={"fact_orders": ("is_priority_order",)},
            model_configs={
                "fact_orders": {
                    "materialized": "incremental",
                    "incremental_strategy": "delete_insert",
                    "cursor": "id",
                    "cursor_type": "integer",
                    "unique_key": "id",
                },
            },
            model_queries={"fact_orders": "SELECT 1 AS id"},
            full_refresh=False,
            expected_action={"fact_orders": PlanAction.CREATE_TABLE},
            expected_reason={"fact_orders": PlanReason.FULL_REFRESH},
            expected_ddl_fragments={
                "fact_orders": "CREATE OR REPLACE TABLE staging.fact_orders AS",
            },
            expected_cascade_action={"fact_orders": BackfillAction.FULL},
            expected_cascade_root_cause={"fact_orders": "is_priority_order"},
        ),
        BuildExecutionPlanTestCase(
            description="changed Python UDF cascades full rebuild to incremental downstream",
            setup_sql=("CREATE TABLE staging.fact_orders AS SELECT 1 AS id",),
            model_locations={"fact_orders": "staging"},
            function_locations={"is_priority_order_py": "staging"},
            function_languages={"is_priority_order_py": FunctionLanguage.PYTHON},
            function_bodies={
                "is_priority_order_py": "def main(value: int) -> int:\n    return value + 2",
            },
            previous_function_bodies={
                "is_priority_order_py": "def main(value: int) -> int:\n    return value + 1",
            },
            function_replay_on_changes={"is_priority_order_py": "full"},
            function_deps={"fact_orders": ("is_priority_order_py",)},
            model_configs={
                "fact_orders": {
                    "materialized": "incremental",
                    "incremental_strategy": "delete_insert",
                    "cursor": "id",
                    "cursor_type": "integer",
                    "unique_key": "id",
                },
            },
            model_queries={"fact_orders": "SELECT 1 AS id"},
            full_refresh=False,
            expected_action={"fact_orders": PlanAction.CREATE_TABLE},
            expected_reason={"fact_orders": PlanReason.FULL_REFRESH},
            expected_ddl_fragments={
                "fact_orders": "CREATE OR REPLACE TABLE staging.fact_orders AS",
            },
            expected_cascade_action={"fact_orders": BackfillAction.FULL},
            expected_cascade_root_cause={"fact_orders": "is_priority_order_py"},
        ),
        BuildExecutionPlanTestCase(
            description=(
                "downstream local bounded policy replaces upstream full and propagates downstream"
            ),
            setup_sql=(
                "CREATE TABLE staging.fact_orders AS SELECT 1 AS id",
                "CREATE TABLE staging.order_metrics AS SELECT 1 AS id",
            ),
            model_locations={
                "stg_orders": "staging",
                "fact_orders": "staging",
                "order_metrics": "staging",
            },
            model_configs={
                "stg_orders": {"materialized": "table"},
                "fact_orders": {
                    "materialized": "incremental",
                    "incremental_strategy": "delete_insert",
                    "cursor": "id",
                    "cursor_type": "integer",
                    "unique_key": "id",
                    "replay_on_change": "bounded-1d",
                },
                "order_metrics": {
                    "materialized": "incremental",
                    "incremental_strategy": "delete_insert",
                    "cursor": "id",
                    "cursor_type": "integer",
                    "unique_key": "id",
                },
            },
            model_queries={
                "stg_orders": "SELECT 1 AS id",
                "fact_orders": "SELECT id FROM stg_orders",
                "order_metrics": "SELECT id FROM fact_orders",
            },
            model_deps={
                "fact_orders": ("stg_orders",),
                "order_metrics": ("fact_orders",),
            },
            full_refresh=False,
            expected_action={
                "stg_orders": PlanAction.CREATE_TABLE,
                "fact_orders": PlanAction.INCREMENTAL_DELETE_INSERT,
                "order_metrics": PlanAction.INCREMENTAL_DELETE_INSERT,
            },
            expected_reason={
                "stg_orders": PlanReason.FIRST_RUN,
                "fact_orders": PlanReason.NORMAL_INCREMENTAL,
                "order_metrics": PlanReason.NORMAL_INCREMENTAL,
            },
            expected_cascade_action={
                "fact_orders": BackfillAction.BOUNDED,
                "order_metrics": BackfillAction.BOUNDED,
            },
            expected_cascade_duration={
                "fact_orders": "1d",
                "order_metrics": "1d",
            },
            expected_cascade_root_cause={
                "fact_orders": "stg_orders",
                "order_metrics": "stg_orders",
            },
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_upstream_first_run_when_building_plan_then_cascades_to_downstream(
    test_case: BuildExecutionPlanTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    sql: str
    for sql in test_case.setup_sql:
        connection.execute(sql)
    write_previous_function_fingerprints(
        test_case=test_case,
        adapter=adapter,
        connection=connection,
    )

    project: Any = build_project_from_test_case(test_case)

    plan: PlanOutput = build_execution_plan_from_kwargs(
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

    expected_reason: PlanReason
    for model_name, expected_reason in test_case.expected_reason.items():
        assert entry_map[model_name].reason == expected_reason

    expected_fragment: str
    for model_name, expected_fragment in test_case.expected_ddl_fragments.items():
        assert expected_fragment in entry_map[model_name].logical_ddl

    expected_cascade_action: BackfillAction
    for model_name, expected_cascade_action in test_case.expected_cascade_action.items():
        cascade: CascadeResult | None = entry_map[model_name].cascade
        assert cascade is not None
        assert cascade.effective_action == expected_cascade_action

    expected_cascade_duration: str | None
    for model_name, expected_cascade_duration in test_case.expected_cascade_duration.items():
        cascade_for_duration: CascadeResult | None = entry_map[model_name].cascade
        assert cascade_for_duration is not None
        assert cascade_for_duration.effective_duration == expected_cascade_duration

    expected_root: str
    for model_name, expected_root in test_case.expected_cascade_root_cause.items():
        cascade_for_root: CascadeResult | None = entry_map[model_name].cascade
        assert cascade_for_root is not None
        assert cascade_for_root.root_cause == expected_root


@pytest.mark.parametrize(
    "test_case",
    [
        FormatPlanIntegrationTestCase(
            description="new project formats with first run group and seeds",
            setup_sql=(),
            model_locations={
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
            seed_locations={"country_codes": "staging"},
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
            model_locations={
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
    ],
    ids=lambda case: case.description,
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

    plan: PlanOutput = build_execution_plan_from_kwargs(
        project=project,
        adapter=adapter,
        connection=connection,
        full_refresh=test_case.full_refresh,
    )

    result: str = format_plan(plan=plan, full_refresh=test_case.full_refresh)

    fragment: str
    for fragment in test_case.expected_format_fragments:
        assert fragment in result, f"Expected '{fragment}' in output:\n{result}"
    for fragment in test_case.unexpected_format_fragments:
        assert fragment not in result, f"Did not expect '{fragment}' in output:\n{result}"
