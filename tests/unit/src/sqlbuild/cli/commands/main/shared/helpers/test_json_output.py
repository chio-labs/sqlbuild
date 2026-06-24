"""Tests for JSON output serialization."""

from __future__ import annotations

import json

import pytest

from sqlbuild.cli.commands.main.shared.helpers.output.json import (
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
    RelationReuseKind,
    WarningSeverity,
)
from sqlbuild.compiler.python_nodes.types import (
    PythonIdentityStatus,
    PythonNodeKind,
    PythonRunPhase,
)
from tests.unit.src.sqlbuild.cli.commands.main.plan.helpers.helpers import (
    build_dependency_baseline_entry,
    build_discovered_provider_usage,
    build_existing_destination_input_entry,
    build_model_entry,
    build_plan_output,
    build_plan_provider_usage,
    build_relation_reuse_plan,
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
        description="plan json includes model identity diagnostics",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="fact_orders",
                    action=PlanAction.INCREMENTAL_DELETE_INSERT,
                    reason=PlanReason.QUERY_CHANGED,
                    fingerprint_version_hash="expected_hash",
                    previous_version_hash="built_hash",
                ),
                build_model_entry(
                    name="dim_customers",
                    action=PlanAction.CREATE_TABLE,
                    reason=PlanReason.FIRST_RUN,
                    fingerprint_version_hash="expected_first_hash",
                ),
            ),
        ),
        expected_keys=("models",),
        expected_fragments=(
            '"expected_version_hash": "expected_hash"',
            '"built_version_hash": "built_hash"',
            '"built_version_present": true',
            '"identity_status": "stale"',
            '"expected_version_hash": "expected_first_hash"',
            '"built_version_hash": null',
            '"built_version_present": false',
            '"identity_status": "missing"',
        ),
    ),
    JsonOutputTestCase(
        description="plan json reports unknown identity when expected hash is unavailable",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="orders",
                    action=PlanAction.CREATE_TABLE,
                    reason=PlanReason.NO_CHANGE,
                    previous_version_hash="built_hash",
                ),
            ),
        ),
        expected_keys=("models",),
        expected_fragments=(
            '"expected_version_hash": null',
            '"built_version_hash": "built_hash"',
            '"built_version_present": true',
            '"identity_status": "unknown"',
        ),
    ),
    JsonOutputTestCase(
        description="plan json includes relation reuse metadata",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="orders",
                    action=PlanAction.CREATE_TABLE,
                    reason=PlanReason.FIRST_RUN,
                    materialization_type=MaterializationType.TABLE,
                    relation_reuse=build_relation_reuse_plan(
                        kind=RelationReuseKind.COMPLETE_RELATION_REUSE,
                        reuse_from_target_name="prod",
                        origin_schema="prod_marts",
                        origin_name="orders",
                        hard_copy=True,
                    ),
                ),
            ),
        ),
        expected_keys=("models",),
        expected_fragments=(
            '"relation_reuse"',
            '"kind": "complete_relation_reuse"',
            '"reuse_from_target": "prod"',
            '"origin_relation": "prod_marts.orders"',
            '"hard_copy": true',
        ),
    ),
    JsonOutputTestCase(
        description="plan json includes shaped reuse categories",
        plan_output=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="orders",
                    action=PlanAction.CREATE_TABLE,
                    reason=PlanReason.FIRST_RUN,
                    relation_reuse=build_relation_reuse_plan(origin_name="orders"),
                ),
            ),
            dependency_baseline_entries=(
                build_dependency_baseline_entry(name="stg_orders"),
                build_dependency_baseline_entry(name="stg_payments", trusted_input=True),
            ),
            existing_destination_input_entries=(
                build_existing_destination_input_entry(name="stg_customers", status="stale"),
            ),
        ),
        expected_keys=("reuse", "existing_destination_inputs"),
        expected_fragments=(
            '"cloned_selected"',
            '"reused_inputs"',
            '"trusted_inputs"',
            '"existing_destination_inputs"',
            '"trusted_input": true',
            '"status": "stale"',
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
            '"reason": "first_run"',
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
                phase=PythonRunPhase.PRE_SQL_INGRESS,
            ),
            PythonPlanEntry(
                name="export_orders",
                kind=PythonNodeKind.ASSET,
                phase=PythonRunPhase.READ_SIDE,
            ),
        ),
        expected_keys=("python_node_count", "python_nodes"),
        expected_fragments=(
            '"python_node_count": 2',
            '"name": "prepare_orders"',
            '"kind": "task"',
            '"phase": "pre_sql_ingress"',
            '"name": "export_orders"',
            '"kind": "asset"',
            '"phase": "read_side"',
        ),
    ),
    JsonOutputTestCase(
        description="plan json includes changed python identity diffs",
        plan_output=build_plan_output(),
        python_plan_entries=(
            PythonPlanEntry(
                name="prepare_orders",
                kind=PythonNodeKind.TASK,
                phase=PythonRunPhase.PRE_SQL_INGRESS,
                identity_status=PythonIdentityStatus.CHANGED,
                previous_definition_json=json.dumps(
                    {"source_text": "def prepare_orders(ctx):\n    return 1\n"},
                    sort_keys=True,
                ),
                current_definition_json=json.dumps(
                    {"source_text": "def prepare_orders(ctx):\n    return 2\n"},
                    sort_keys=True,
                ),
                previous_metadata_json=json.dumps(
                    {
                        "dependencies": [
                            {
                                "module": "tasks.helpers",
                                "qualname": "order_label",
                                "source_path": "tasks/helpers.py",
                                "source_text": "def order_label():\n    return 'old'\n",
                            }
                        ]
                    },
                    sort_keys=True,
                ),
                current_metadata_json=json.dumps(
                    {
                        "dependencies": [
                            {
                                "module": "tasks.helpers",
                                "qualname": "order_label",
                                "source_path": "tasks/helpers.py",
                                "source_text": "def order_label():\n    return 'new'\n",
                            }
                        ]
                    },
                    sort_keys=True,
                ),
            ),
        ),
        expected_keys=("python_nodes",),
        expected_fragments=(
            '"identity_diff"',
            '"source_diff"',
            '"dependency_diff"',
            '"-    return 1"',
            '"+    return 2"',
            "tasks/helpers.py :: tasks.helpers :: order_label",
            "\"-    return 'old'\"",
            "\"+    return 'new'\"",
        ),
    ),
    JsonOutputTestCase(
        description="plan json includes provider usage metadata",
        plan_output=build_plan_output(
            provider_usages=(
                build_plan_provider_usage(
                    provider_name="marker_provider",
                    consumer_kind="loader",
                    consumer_name="raw_orders",
                ),
            ),
        ),
        python_plan_entries=(
            PythonPlanEntry(
                name="publish_orders",
                kind=PythonNodeKind.TASK,
                phase=PythonRunPhase.READ_SIDE,
                provider_usages=(build_discovered_provider_usage(),),
            ),
        ),
        expected_keys=("providers",),
        expected_fragments=(
            '"providers"',
            '"name": "marker_provider"',
            '"used_by"',
            '"kind": "loader"',
            '"name": "raw_orders"',
            '"kind": "task"',
            '"name": "publish_orders"',
            '"parameter": "marker_provider"',
            '"class_name": "MarkerProvider"',
            '"module": "providers.marker"',
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
