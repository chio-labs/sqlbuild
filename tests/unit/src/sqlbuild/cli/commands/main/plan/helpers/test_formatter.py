"""Tests for plan output formatting."""

from __future__ import annotations

import pytest

from sqlbuild.cli.commands.main.plan.helpers.formatter import (
    format_plan_compact,
    format_plan_verbose,
)
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

COMPACT_TEST_CASES: list[FormatPlanTestCase] = [
    FormatPlanTestCase(
        description="compact output shows plan ready and model counts",
        plan_output=build_plan_output(
            model_entries=(build_model_entry(name="orders", action=PlanAction.CREATE_TABLE),),
        ),
        expected_fragments=("Plan ready", "Selected models: 1", "Will run: 1", "orders"),
    ),
    FormatPlanTestCase(
        description="compact output hides skipped models from will-run section",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="orders", action=PlanAction.SKIP, reason=PlanReason.NO_CHANGE
                ),
            ),
        ),
        expected_fragments=("Will run: 0",),
        unexpected_fragments=("Will run\n",),
    ),
    FormatPlanTestCase(
        description="compact output shows reason and action for running models",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="fact_orders",
                    action=PlanAction.CREATE_TABLE,
                    reason=PlanReason.QUERY_CHANGED,
                    backfill_action=BackfillAction.BOUNDED,
                    backfill_duration="30d",
                ),
            ),
        ),
        expected_fragments=(
            "fact_orders",
            "reason: query changed",
            "action: bounded backfill (30d)",
            "policy: query_change_backfill=bounded(30d)",
        ),
    ),
    FormatPlanTestCase(
        description="compact output shows warnings section when warnings exist",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="orders", action=PlanAction.SKIP, reason=PlanReason.NO_CHANGE
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
        expected_fragments=("Warnings: 1", "stg_customers", "type change detected"),
    ),
    FormatPlanTestCase(
        description="compact output shows diffs available hint when previous sql exists",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="orders",
                    action=PlanAction.CREATE_TABLE,
                    reason=PlanReason.QUERY_CHANGED,
                    previous_query_sql="SELECT 1",
                ),
            ),
        ),
        expected_fragments=("Diffs available for:", "orders", "sqb plan --verbose"),
    ),
]

VERBOSE_TEST_CASES: list[FormatPlanTestCase] = [
    FormatPlanTestCase(
        description="verbose output shows query diff between previous and current sql",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="orders",
                    action=PlanAction.CREATE_TABLE,
                    reason=PlanReason.QUERY_CHANGED,
                    previous_query_sql="SELECT order_id\nFROM raw_orders",
                ),
            ),
        ),
        expected_fragments=("query diff:", "previous", "current"),
    ),
    FormatPlanTestCase(
        description="verbose output shows schema diff for schema change findings",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="orders",
                    action=PlanAction.CREATE_TABLE,
                    reason=PlanReason.SCHEMA_CHANGED,
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
        expected_fragments=("schema diff:", "+ discount", "added"),
    ),
    FormatPlanTestCase(
        description="verbose output shows no previous fingerprint for first run models",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="new_model",
                    action=PlanAction.CREATE_TABLE,
                    reason=PlanReason.FIRST_RUN,
                ),
            ),
        ),
        expected_fragments=("new_model", "new model", "no previous fingerprint"),
    ),
    FormatPlanTestCase(
        description="verbose output shows schema diff in warnings for warning models",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="stg_customers",
                    action=PlanAction.SKIP,
                    reason=PlanReason.NO_CHANGE,
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
            warnings=(
                build_warning(
                    model_name="stg_customers",
                    message="type change detected",
                ),
            ),
        ),
        expected_fragments=(
            "stg_customers",
            "type change detected",
            "schema diff:",
            "~ customer_id",
            "VARCHAR",
            "INTEGER",
            "type changed",
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    COMPACT_TEST_CASES,
    ids=[case.description for case in COMPACT_TEST_CASES],
)
def test_given_plan_output_when_formatting_compact_then_contains_expected_fragments(
    test_case: FormatPlanTestCase,
) -> None:
    result: str = format_plan_compact(test_case.plan_output)

    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in result, f"Expected '{fragment}' in compact output"
    for fragment in test_case.unexpected_fragments:
        assert fragment not in result, f"Did not expect '{fragment}' in compact output"


@pytest.mark.parametrize(
    "test_case",
    VERBOSE_TEST_CASES,
    ids=[case.description for case in VERBOSE_TEST_CASES],
)
def test_given_plan_output_when_formatting_verbose_then_contains_expected_fragments(
    test_case: FormatPlanTestCase,
) -> None:
    result: str = format_plan_verbose(test_case.plan_output)

    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in result, f"Expected '{fragment}' in verbose output"
    for fragment in test_case.unexpected_fragments:
        assert fragment not in result, f"Did not expect '{fragment}' in verbose output"
