"""Tests for plan output formatting."""

from __future__ import annotations

import pytest

from sqlbuild.cli.commands.main.helpers.plan.formatter import format_plan
from sqlbuild.compiler.compile.types import FunctionLanguage
from sqlbuild.compiler.planner.models import CascadeCause, CascadeResult, CursorBounds
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    MaterializationType,
    PlanAction,
    PlanReason,
    SchemaChangeKind,
    WarningSeverity,
)
from tests.unit.src.sqlbuild.cli.commands.main.plan.helpers._test_types import (
    FormatPlanTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.plan.helpers.helpers import (
    build_function_entry,
    build_model_entry,
    build_plan_output,
    build_schema_finding,
    build_seed_entry,
    build_warning,
)

TEST_CASES: list[FormatPlanTestCase] = [
    FormatPlanTestCase(
        description="routine models section shows names with strategy and cursor type",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="stg_orders",
                    action=PlanAction.CREATE_VIEW,
                    reason=PlanReason.NO_CHANGE,
                    materialization_type=MaterializationType.VIEW,
                ),
                build_model_entry(
                    name="fact_orders",
                    action=PlanAction.INCREMENTAL_DELETE_INSERT,
                    reason=PlanReason.NORMAL_INCREMENTAL,
                    materialization_type=MaterializationType.INCREMENTAL,
                    incremental_strategy="delete_insert",
                    cursor_type="timestamp",
                ),
                build_model_entry(
                    name="fact_events",
                    action=PlanAction.INCREMENTAL_DELETE_INSERT,
                    reason=PlanReason.NORMAL_INCREMENTAL,
                    materialization_type=MaterializationType.INCREMENTAL,
                    incremental_strategy="delete_insert",
                    cursor_type="integer",
                    incremental_mode="microbatch",
                ),
            ),
        ),
        expected_fragments=(
            "Models (3 standard run)",
            "stg_orders",
            "fact_orders",
            "fact_events",
            "delete_insert (timestamp)",
            "delete_insert (integer, microbatch)",
            "view",
        ),
        unexpected_fragments=("Normal",),
    ),
    FormatPlanTestCase(
        description="first run shows materialization label with strategy and microbatch",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="stg_orders",
                    action=PlanAction.CREATE_VIEW,
                    reason=PlanReason.FIRST_RUN,
                    materialization_type=MaterializationType.VIEW,
                ),
                build_model_entry(
                    name="fact_orders",
                    action=PlanAction.CREATE_TABLE,
                    reason=PlanReason.FIRST_RUN,
                    materialization_type=MaterializationType.INCREMENTAL,
                    incremental_strategy="delete_insert",
                    cursor_type="timestamp",
                    incremental_mode="microbatch",
                ),
            ),
        ),
        expected_fragments=(
            "First run (2)",
            "stg_orders",
            "view",
            "fact_orders",
            "delete_insert (timestamp, microbatch)",
        ),
    ),
    FormatPlanTestCase(
        description="snapshot models show strategy and historical shape labels",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="customer_current_snapshot",
                    action=PlanAction.SNAPSHOT,
                    reason=PlanReason.FIRST_RUN,
                    materialization_type=MaterializationType.SNAPSHOT,
                    snapshot_strategy="timestamp",
                ),
                build_model_entry(
                    name="customer_daily_snapshot",
                    action=PlanAction.SNAPSHOT,
                    reason=PlanReason.FIRST_RUN,
                    materialization_type=MaterializationType.SNAPSHOT,
                    snapshot_strategy="check",
                    observed_at_column="observed_at",
                    historical_input="snapshot",
                ),
                build_model_entry(
                    name="customer_changes_snapshot",
                    action=PlanAction.SNAPSHOT,
                    reason=PlanReason.FIRST_RUN,
                    materialization_type=MaterializationType.SNAPSHOT,
                    snapshot_strategy="timestamp",
                    observed_at_column="loaded_at",
                    historical_input="changes",
                ),
            ),
        ),
        expected_fragments=(
            "First run (3)",
            "customer_current_snapshot",
            "snapshot (timestamp)",
            "customer_daily_snapshot",
            "snapshot (check, historical snapshot)",
            "customer_changes_snapshot",
            "snapshot (timestamp, historical changes)",
        ),
    ),
    FormatPlanTestCase(
        description="query changed shows action policy cursor and mode",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="fact_orders",
                    action=PlanAction.INCREMENTAL_DELETE_INSERT,
                    reason=PlanReason.QUERY_CHANGED,
                    materialization_type=MaterializationType.INCREMENTAL,
                    backfill_action=BackfillAction.BOUNDED,
                    backfill_duration="30d",
                    cursor_column="event_time",
                    cursor_type="timestamp",
                    incremental_mode="microbatch",
                    cursor_bounds=CursorBounds(start="2026-03-26", end="2026-04-25"),
                    previous_query_sql="SELECT order_id FROM raw",
                ),
            ),
        ),
        expected_fragments=(
            "Query changed (1)",
            "fact_orders",
            "rebuild last 30d",
            "cursor: event_time",
            "mode: microbatch",
            "2026-03-26",
            "2026-04-25",
            "policy: query_change_backfill=bounded-30d",
            "query diff:",
        ),
    ),
    FormatPlanTestCase(
        description="schema changed shows schema diff and policy",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="dim_customers",
                    action=PlanAction.CREATE_TABLE,
                    reason=PlanReason.SCHEMA_CHANGED,
                    backfill_action=BackfillAction.BOUNDED,
                    backfill_duration="7d",
                    schema_findings=(
                        build_schema_finding(
                            kind=SchemaChangeKind.COLUMN_ADDED,
                            column_name="discount",
                            expected_type="FLOAT",
                        ),
                    ),
                ),
            ),
        ),
        expected_fragments=(
            "Schema changed (1)",
            "dim_customers",
            "rebuild last 7d, add column",
            "schema diff:",
            "+ discount",
            "added",
        ),
    ),
    FormatPlanTestCase(
        description="full rebuild hides cursor range placeholders",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="hourly_order_activity",
                    action=PlanAction.CREATE_TABLE,
                    reason=PlanReason.QUERY_CHANGED,
                    materialization_type=MaterializationType.INCREMENTAL,
                    backfill_action=BackfillAction.FULL,
                    cursor_column="activity_hour",
                    cursor_type="timestamp",
                    incremental_mode="microbatch",
                    cursor_bounds=CursorBounds(
                        start="__SQB_CURSOR_START__",
                        end="__SQB_CURSOR_END__",
                    ),
                    previous_query_sql="SELECT activity_hour FROM raw",
                ),
            ),
        ),
        expected_fragments=(
            "hourly_order_activity",
            "full rebuild",
            "cursor: activity_hour",
            "mode: microbatch",
        ),
        unexpected_fragments=(
            "range:",
            "__SQB_CURSOR_START__",
            "__SQB_CURSOR_END__",
        ),
    ),
    FormatPlanTestCase(
        description="upstream changed shows cascade cause",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="fact_daily_revenue",
                    action=PlanAction.INCREMENTAL_DELETE_INSERT,
                    reason=PlanReason.NORMAL_INCREMENTAL,
                    materialization_type=MaterializationType.INCREMENTAL,
                    incremental_strategy="delete_insert",
                    cursor_column="event_time",
                    cursor_type="timestamp",
                    backfill_action=BackfillAction.WARN_ONLY,
                    cascade=CascadeResult(
                        effective_action=BackfillAction.BOUNDED,
                        effective_duration="90d",
                        root_cause="fact_orders",
                        causes=(
                            CascadeCause(
                                model_name="fact_orders",
                                effective_action=BackfillAction.BOUNDED,
                                effective_duration="90d",
                            ),
                        ),
                    ),
                ),
            ),
        ),
        expected_fragments=(
            "Upstream changed (1)",
            "fact_daily_revenue",
            "rebuild last 90d",
            "cause: fact_orders (90d)",
        ),
        unexpected_fragments=("Normal",),
    ),
    FormatPlanTestCase(
        description="upstream changed with full shows full in cause",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="dim_summary",
                    action=PlanAction.CREATE_TABLE,
                    reason=PlanReason.NO_CHANGE,
                    cascade=CascadeResult(
                        effective_action=BackfillAction.FULL,
                        effective_duration=None,
                        root_cause="fact_orders",
                        causes=(
                            CascadeCause(
                                model_name="fact_orders",
                                effective_action=BackfillAction.FULL,
                                effective_duration=None,
                            ),
                        ),
                    ),
                ),
            ),
        ),
        expected_fragments=(
            "Upstream changed (1)",
            "dim_summary",
            "full rebuild",
            "cause: fact_orders (full)",
        ),
    ),
    FormatPlanTestCase(
        description="seeds section shows seed names",
        plan_output=build_plan_output(
            model_entries=(build_model_entry(name="orders", action=PlanAction.CREATE_TABLE),),
            seed_entries=(build_seed_entry(name="country_codes"),),
        ),
        expected_fragments=(
            "Seeds (1)",
            "country_codes",
        ),
    ),
    FormatPlanTestCase(
        description="functions section shows names and udf language",
        plan_output=build_plan_output(
            model_entries=(build_model_entry(name="orders", action=PlanAction.CREATE_TABLE),),
            function_entries=(
                build_function_entry(name="is_completed_order", language=FunctionLanguage.SQL),
                build_function_entry(
                    name="is_completed_order_py", language=FunctionLanguage.PYTHON
                ),
            ),
        ),
        expected_fragments=(
            "Plan ready (3 selected)",
            "Functions (2 standard run)",
            "is_completed_order",
            "sql udf",
            "is_completed_order_py",
            "python udf",
        ),
    ),
    FormatPlanTestCase(
        description="function query change shows diff and policy",
        plan_output=build_plan_output(
            model_entries=(build_model_entry(name="orders", action=PlanAction.CREATE_TABLE),),
            function_entries=(
                build_function_entry(
                    name="is_completed_order",
                    language=FunctionLanguage.SQL,
                    reason=PlanReason.QUERY_CHANGED,
                    backfill_action=BackfillAction.FULL,
                    previous_query_sql="returns=BOOLEAN\nbody=\norder_status = 'completed'",
                ),
            ),
        ),
        expected_fragments=(
            "Changed functions (1)",
            "is_completed_order",
            "sql udf",
            "policy: query_change_backfill=full",
            "query diff:",
            "--- previous",
            "+++ current",
        ),
    ),
    FormatPlanTestCase(
        description="upstream changed prefers root function query cause",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="daily_activity_rollup",
                    action=PlanAction.CREATE_TABLE,
                    reason=PlanReason.NO_CHANGE,
                    cascade=CascadeResult(
                        effective_action=BackfillAction.FULL,
                        effective_duration=None,
                        root_cause="is_completed_order",
                        root_reason=PlanReason.QUERY_CHANGED,
                        causes=(
                            CascadeCause(
                                model_name="hourly_order_activity",
                                effective_action=BackfillAction.FULL,
                                effective_duration=None,
                            ),
                        ),
                    ),
                ),
            ),
        ),
        expected_fragments=(
            "Upstream changed (1)",
            "daily_activity_rollup",
            "full rebuild",
            "cause: is_completed_order (query changed)",
        ),
        unexpected_fragments=("cause: hourly_order_activity", "cause: is_completed_order (full)"),
    ),
    FormatPlanTestCase(
        description="warnings section shows warning messages",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="orders",
                    action=PlanAction.SKIP,
                    reason=PlanReason.NO_CHANGE,
                    backfill_action=BackfillAction.WARN_ONLY,
                ),
            ),
            warnings=(
                build_warning(
                    model_name="stg_customers",
                    message="type change detected",
                    severity=WarningSeverity.WARNING,
                ),
            ),
        ),
        expected_fragments=(
            "Warnings (1)",
            "stg_customers",
            "type change detected",
        ),
    ),
    FormatPlanTestCase(
        description="full refresh shows aggregate counts with incremental detail",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="stg_orders",
                    action=PlanAction.CREATE_VIEW,
                    reason=PlanReason.FULL_REFRESH,
                    materialization_type=MaterializationType.VIEW,
                ),
                build_model_entry(
                    name="dim_customers",
                    action=PlanAction.CREATE_TABLE,
                    reason=PlanReason.FULL_REFRESH,
                ),
                build_model_entry(
                    name="fact_orders",
                    action=PlanAction.CREATE_TABLE,
                    reason=PlanReason.FULL_REFRESH,
                    materialization_type=MaterializationType.INCREMENTAL,
                    incremental_strategy="delete_insert",
                    cursor_type="timestamp",
                    incremental_mode="microbatch",
                ),
            ),
        ),
        full_refresh=True,
        expected_fragments=(
            "Plan ready (full refresh, 3 selected)",
            "Full refresh (3)",
            "view",
            "table",
            "delete_insert (timestamp, microbatch)",
        ),
        unexpected_fragments=("Normal", "Query changed", "First run"),
    ),
    FormatPlanTestCase(
        description="empty plan shows only header and selected zero",
        plan_output=build_plan_output(),
        expected_fragments=("Plan ready (0 selected)",),
        unexpected_fragments=("Normal", "Seeds", "Warnings"),
    ),
    FormatPlanTestCase(
        description="non-microbatch incremental omits mode line",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="fact_orders",
                    action=PlanAction.INCREMENTAL_DELETE_INSERT,
                    reason=PlanReason.QUERY_CHANGED,
                    materialization_type=MaterializationType.INCREMENTAL,
                    backfill_action=BackfillAction.BOUNDED,
                    backfill_duration="30d",
                    cursor_column="event_time",
                    cursor_type="timestamp",
                ),
            ),
        ),
        expected_fragments=("cursor: event_time",),
        unexpected_fragments=("mode:",),
    ),
    FormatPlanTestCase(
        description="custom materialization shows name with custom suffix in normal section",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="fact_orders",
                    action=PlanAction.CUSTOM,
                    reason=PlanReason.NO_CHANGE,
                    materialization_type=MaterializationType.CUSTOM,
                    custom_materialization_name="partition_tracked",
                ),
            ),
        ),
        expected_fragments=("partition_tracked (custom)",),
    ),
    FormatPlanTestCase(
        description="custom materialization shows name with custom suffix in first run section",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="fact_orders",
                    action=PlanAction.CUSTOM,
                    reason=PlanReason.FIRST_RUN,
                    materialization_type=MaterializationType.CUSTOM,
                    custom_materialization_name="atomic_swap",
                ),
            ),
        ),
        expected_fragments=("atomic_swap (custom)",),
    ),
    FormatPlanTestCase(
        description="changed sections appear before routine resource sections",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="fact_orders",
                    action=PlanAction.CREATE_TABLE,
                    reason=PlanReason.QUERY_CHANGED,
                    backfill_action=BackfillAction.FULL,
                    previous_query_sql="SELECT order_id FROM raw",
                ),
                build_model_entry(
                    name="stg_orders",
                    action=PlanAction.CREATE_VIEW,
                    reason=PlanReason.NO_CHANGE,
                    materialization_type=MaterializationType.VIEW,
                ),
            ),
            function_entries=(
                build_function_entry(name="is_completed_order"),
                build_function_entry(
                    name="normalize_email",
                    reason=PlanReason.QUERY_CHANGED,
                    backfill_action=BackfillAction.FULL,
                    previous_query_sql="returns=TEXT\nbody=old_email",
                ),
            ),
            seed_entries=(build_seed_entry(name="waffle_types"),),
        ),
        expected_fragments=(
            "normalize_email",
            "is_completed_order",
            "fact_orders",
            "stg_orders",
            "waffle_types",
        ),
        unexpected_fragments=("Functions (2", "Models (2"),
        expected_ordered_fragments=(
            "Changed functions (1)",
            "Query changed (1)",
            "Models (1 standard run)",
            "Functions (1 standard run)",
            "Seeds (1)",
        ),
    ),
    FormatPlanTestCase(
        description="detail rows align value column to longest displayed name",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="hourly_activity_with_daily_context",
                    action=PlanAction.INCREMENTAL_DELETE_INSERT,
                    reason=PlanReason.FIRST_RUN,
                    materialization_type=MaterializationType.INCREMENTAL,
                    incremental_strategy="delete_insert",
                    cursor_type="timestamp",
                    incremental_mode="microbatch",
                ),
                build_model_entry(
                    name="order_status_index",
                    action=PlanAction.INCREMENTAL_DELETE_INSERT,
                    reason=PlanReason.FIRST_RUN,
                    materialization_type=MaterializationType.INCREMENTAL,
                    incremental_strategy="delete_insert",
                    cursor_type="integer",
                ),
            ),
        ),
        expected_fragments=(
            "  hourly_activity_with_daily_context delete_insert (timestamp, microbatch)",
            "  order_status_index                 delete_insert (integer)",
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_plan_output_when_formatting_then_contains_expected_fragments(
    test_case: FormatPlanTestCase,
) -> None:
    result: str = format_plan(
        test_case.plan_output,
        full_refresh=test_case.full_refresh,
        use_color=False,
    )

    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in result, f"Expected '{fragment}' in output:\n{result}"
    for fragment in test_case.unexpected_fragments:
        assert fragment not in result, f"Did not expect '{fragment}' in output:\n{result}"
    previous_index: int = -1
    for fragment in test_case.expected_ordered_fragments:
        current_index: int = result.index(fragment)
        assert current_index > previous_index, result
        previous_index = current_index
