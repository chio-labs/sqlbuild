"""Tests for plan output formatting."""

from __future__ import annotations

import pytest

from sqlbuild.cli.commands.main.plan.helpers.formatter import format_plan
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    PlanAction,
    PlanReason,
    SchemaChangeKind,
    WarningSeverity,
)
from tests.unit.src.sqlbuild.cli.commands.main.plan.helpers._test_types import (
    FormatPlanTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.plan.helpers.helpers import (
    build_model_entry,
    build_plan_output,
    build_schema_finding,
    build_warning,
)

TEST_CASES: list[FormatPlanTestCase] = [
    FormatPlanTestCase(
        description="first run models do not show action detail",
        plan_output=build_plan_output(
            model_entries=(build_model_entry(name="orders", action=PlanAction.CREATE_TABLE),),
        ),
        unexpected_fragments=("rebuild", "policy:", "cursor:"),
    ),
    FormatPlanTestCase(
        description="query changed group shows action and policy inline",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="fact_orders",
                    action=PlanAction.CREATE_TABLE,
                    reason=PlanReason.QUERY_CHANGED,
                    backfill_action=BackfillAction.BOUNDED,
                    backfill_duration="30d",
                    previous_query_sql="SELECT order_id FROM raw",
                ),
            ),
        ),
        expected_fragments=(
            "Query changed (1)",
            "fact_orders",
            "rebuild last 30d",
            "policy: query_change_backfill=bounded(30d)",
            "query diff:",
        ),
    ),
    FormatPlanTestCase(
        description="schema changed group shows schema diff and action",
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
        description="normal models shown as count in header not listed",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="stg_orders",
                    action=PlanAction.CREATE_TABLE,
                    reason=PlanReason.NO_CHANGE,
                ),
                build_model_entry(
                    name="fact_orders",
                    action=PlanAction.CREATE_TABLE,
                    reason=PlanReason.QUERY_CHANGED,
                    backfill_action=BackfillAction.BOUNDED,
                    backfill_duration="30d",
                ),
            ),
        ),
        expected_fragments=("Normal: 1", "Query changed (1)"),
        unexpected_fragments=("stg_orders",),
    ),
    FormatPlanTestCase(
        description="warnings section shows warning messages",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="orders",
                    action=PlanAction.SKIP,
                    reason=PlanReason.NO_CHANGE,
                ),
            ),
            warnings=(
                build_warning(
                    model_name="stg_customers",
                    message="type change detected, no on_schema_change configured",
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
        description="schema changed with full rebuild shows type change suffix",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="stg_payments",
                    action=PlanAction.CREATE_TABLE,
                    reason=PlanReason.SCHEMA_CHANGED,
                    backfill_action=BackfillAction.FULL,
                    schema_findings=(
                        build_schema_finding(
                            kind=SchemaChangeKind.COLUMN_TYPE_CHANGED,
                            column_name="customer_id",
                            expected_type="VARCHAR",
                            actual_type="INTEGER",
                        ),
                    ),
                ),
            ),
        ),
        expected_fragments=(
            "stg_payments",
            "full rebuild, type change",
            "~ customer_id",
            "VARCHAR",
            "INTEGER",
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
    result: str = format_plan(test_case.plan_output)

    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in result, f"Expected '{fragment}' in output:\n{result}"
    for fragment in test_case.unexpected_fragments:
        assert fragment not in result, f"Did not expect '{fragment}' in output:\n{result}"
