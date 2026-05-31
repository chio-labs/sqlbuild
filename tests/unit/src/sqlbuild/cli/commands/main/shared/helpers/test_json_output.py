"""Tests for JSON output serialization."""

from __future__ import annotations

import json

import pytest

from sqlbuild.cli.commands.main.shared.helpers.json_output import (
    format_compile_json,
    format_plan_json,
)
from sqlbuild.compiler.pipeline.models import PythonPlanEntry
from sqlbuild.compiler.planner.models import CascadeCause, CascadeResult
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    MaterializationType,
    PlanAction,
    PlanReason,
    WarningSeverity,
)
from sqlbuild.compiler.python_nodes.types import PythonNodeKind, PythonRunRegion
from tests.unit.src.sqlbuild.cli.commands.main.plan.helpers.helpers import (
    build_model_entry,
    build_plan_output,
    build_seed_entry,
    build_source_load_entry,
    build_warning,
)
from tests.unit.src.sqlbuild.cli.commands.main.shared.helpers._test_types import (
    JsonOutputTestCase,
)

PLAN_JSON_TEST_CASES: list[JsonOutputTestCase] = [
    JsonOutputTestCase(
        description="plan json includes model action reason and backfill",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="fact_orders",
                    action=PlanAction.INCREMENTAL_DELETE_INSERT,
                    reason=PlanReason.QUERY_CHANGED,
                    materialization_type=MaterializationType.INCREMENTAL,
                    incremental_strategy="delete_insert",
                    cursor_type="timestamp",
                    backfill_action=BackfillAction.BOUNDED,
                    backfill_duration="30d",
                ),
            ),
        ),
        expected_keys=("selected_count", "models", "seeds", "warnings"),
        expected_fragments=(
            '"action": "incremental_delete_insert"',
            '"reason": "query_changed"',
            '"incremental_strategy": "delete_insert"',
            '"cursor_type": "timestamp"',
            '"duration": "30d"',
        ),
    ),
    JsonOutputTestCase(
        description="plan json includes cascade when present",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="fact_daily",
                    action=PlanAction.CREATE_TABLE,
                    reason=PlanReason.NO_CHANGE,
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
        expected_keys=("selected_count", "models"),
        expected_fragments=(
            '"reason": "upstream_changed"',
            '"cascade"',
            '"root_cause": "fact_orders"',
            '"effective_duration": "90d"',
        ),
    ),
    JsonOutputTestCase(
        description="plan json includes seeds and warnings",
        plan_output=build_plan_output(
            model_entries=(build_model_entry(name="orders", action=PlanAction.CREATE_TABLE),),
            seed_entries=(build_seed_entry(name="country_codes"),),
            warnings=(
                build_warning(
                    model_name="stg_customers",
                    message="type change detected",
                    severity=WarningSeverity.WARNING,
                ),
            ),
        ),
        expected_keys=("selected_count", "models", "seeds", "warnings"),
        expected_fragments=(
            '"country_codes"',
            '"type change detected"',
            '"severity": "warning"',
        ),
    ),
    JsonOutputTestCase(
        description="plan json includes source load count",
        plan_output=build_plan_output(
            model_entries=(build_model_entry(name="orders", action=PlanAction.CREATE_TABLE),),
            source_load_entries=(build_source_load_entry(name="raw_orders"),),
        ),
        expected_keys=("selected_count", "source_load_count", "source_loads"),
        expected_fragments=(
            '"selected_count": 1',
            '"source_load_count": 1',
            '"name": "raw_orders"',
        ),
    ),
    JsonOutputTestCase(
        description="plan json includes python node lifecycle entries",
        plan_output=build_plan_output(
            model_entries=(build_model_entry(name="orders", action=PlanAction.CREATE_TABLE),),
        ),
        python_plan_entries=(
            PythonPlanEntry(
                name="prepare_orders",
                kind=PythonNodeKind.TASK,
                region=PythonRunRegion.PRE_SQL_INGRESS,
            ),
            PythonPlanEntry(
                name="export_orders",
                kind=PythonNodeKind.ASSET,
                region=PythonRunRegion.SQL_READ_PYTHON,
            ),
        ),
        expected_keys=("python_node_count", "python_nodes"),
        expected_fragments=(
            '"python_node_count": 2',
            '"name": "prepare_orders"',
            '"kind": "task"',
            '"region": "pre_sql_ingress"',
            '"name": "export_orders"',
            '"kind": "asset"',
            '"region": "sql_read_python"',
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    PLAN_JSON_TEST_CASES,
    ids=[case.description for case in PLAN_JSON_TEST_CASES],
)
def test_given_plan_output_when_formatting_json_then_produces_valid_json(
    test_case: JsonOutputTestCase,
) -> None:
    result: str = format_plan_json(
        test_case.plan_output,
        python_plan_entries=test_case.python_plan_entries,
    )
    parsed: dict[str, object] = json.loads(result)

    key: str
    for key in test_case.expected_keys:
        assert key in parsed, f"Expected key '{key}' in JSON output"

    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in result, f"Expected '{fragment}' in JSON:\n{result}"


@pytest.mark.parametrize(
    "test_case",
    [
        JsonOutputTestCase(
            description="compile json includes model sql and ddl",
            plan_output=build_plan_output(
                model_entries=(
                    build_model_entry(
                        name="orders",
                        action=PlanAction.CREATE_TABLE,
                    ),
                ),
                seed_entries=(build_seed_entry(name="country_codes"),),
            ),
            expected_keys=("model_count", "seed_count", "models", "seeds"),
            expected_fragments=(
                '"resolved_sql"',
                '"logical_ddl"',
                '"model_count": 1',
                '"seed_count": 1',
                '"country_codes"',
            ),
        ),
    ],
    ids=["compile json includes model sql and ddl"],
)
def test_given_plan_output_when_formatting_compile_json_then_produces_valid_json(
    test_case: JsonOutputTestCase,
) -> None:
    result: str = format_compile_json(test_case.plan_output)
    parsed: dict[str, object] = json.loads(result)

    key: str
    for key in test_case.expected_keys:
        assert key in parsed, f"Expected key '{key}' in JSON output"

    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in result, f"Expected '{fragment}' in JSON:\n{result}"
