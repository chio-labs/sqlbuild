"""Tests for execution JSON serialization."""

from __future__ import annotations

import json

import pytest

from sqlbuild.cli.commands.shared.helpers.output.execution_json import (
    format_build_execution_json,
)
from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.compiler.planner.types import MaterializationType, PlanAction, PlanReason
from sqlbuild.compiler.python_nodes.types import PythonNodeKind, PythonNodeStatus
from sqlbuild.executor.build.models import BuildExecutionResult, SeedExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.python_nodes.models import PythonNodeExecutionResult
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.types import ExecutionStatus
from tests.unit.src.sqlbuild.cli.commands.main.plan.helpers.helpers import (
    build_model_entry,
    build_plan_output,
    build_relation_reuse_plan,
    build_seed_entry,
)
from tests.unit.src.sqlbuild.cli.commands.shared.helpers._test_types import (
    ExecutionJsonRelationReuseTestCase,
    ExecutionJsonSeedReasonTestCase,
    ExecutionJsonTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.shared.helpers.helpers import build_audit_result


@pytest.mark.parametrize(
    "test_case",
    [
        ExecutionJsonTestCase(
            description="build json includes Python node assets and summary counts",
            result=BuildExecutionResult(status=BuildStatus.SUCCESS),
            python_node_results=(
                PythonNodeExecutionResult(
                    node_name="export_orders",
                    kind=PythonNodeKind.ASSET,
                    status=PythonNodeStatus.SUCCESS,
                    metadata={"uri": "s3://orders"},
                    materialized=False,
                ),
            ),
            expected_status="success",
            expected_summary={
                "success_count": 1,
                "failure_count": 0,
                "skipped_count": 0,
                "warning_count": 0,
                "python_check_pass_count": 0,
                "python_check_warn_count": 0,
                "python_check_fail_count": 0,
            },
            expected_asset_name="export_orders",
            expected_asset_status="success",
        )
    ],
    ids=["build json includes Python node assets and summary counts"],
)
def test_given_build_result_with_python_nodes_when_formatting_json_then_includes_python_assets(
    test_case: ExecutionJsonTestCase,
) -> None:
    result: str = format_build_execution_json(
        result=test_case.result,
        plan=build_plan_output(),
        python_node_results=test_case.python_node_results,
    )
    payload: dict[str, object] = json.loads(result)
    assets: dict[str, dict[str, object]] = {
        str(asset["name"]): asset
        for asset in payload["assets"]  # type: ignore[index]
    }

    assert payload["status"] == test_case.expected_status
    assert payload["summary"] == test_case.expected_summary
    assert assets[test_case.expected_asset_name]["status"] == test_case.expected_asset_status
    assert assets[test_case.expected_asset_name]["kind"] == "asset"
    assert assets[test_case.expected_asset_name]["metadata"] == {"uri": "s3://orders"}
    assert assets[test_case.expected_asset_name]["materialized"] is False


@pytest.mark.parametrize(
    "test_case",
    [
        ExecutionJsonRelationReuseTestCase(
            description="build json includes relation reuse metadata",
            expected_asset_name="orders",
            expected_relation_reuse={
                "kind": "complete_relation_reuse",
                "reuse_from_target": "prod",
                "origin_relation": "prod_marts.orders",
                "hard_copy": True,
            },
        )
    ],
    ids=["build json includes relation reuse metadata"],
)
def test_given_reused_model_when_formatting_build_json_then_includes_relation_reuse_metadata(
    test_case: ExecutionJsonRelationReuseTestCase,
) -> None:
    result: str = format_build_execution_json(
        result=BuildExecutionResult(
            status=BuildStatus.SUCCESS,
            model_results=(
                ModelExecutionResult(
                    model_name="orders",
                    status=ExecutionStatus.SUCCESS,
                    promoted_relation="dev.orders",
                ),
            ),
        ),
        plan=build_plan_output(
            model_entries=(
                build_model_entry(
                    name="orders",
                    action=PlanAction.CREATE_TABLE,
                    reason=PlanReason.FIRST_RUN,
                    materialization_type=MaterializationType.TABLE,
                    relation_reuse=build_relation_reuse_plan(
                        origin_schema="prod_marts",
                        origin_name="orders",
                        hard_copy=True,
                    ),
                ),
            ),
        ),
    )
    payload: dict[str, object] = json.loads(result)
    assets: list[dict[str, object]] = payload["assets"]  # type: ignore[assignment]

    assert assets[0]["name"] == test_case.expected_asset_name
    assert assets[0]["relation_reuse"] == test_case.expected_relation_reuse


@pytest.mark.parametrize(
    "test_case",
    [
        ExecutionJsonRelationReuseTestCase(
            description="build json includes reused audit marker",
            expected_asset_name="orders",
            expected_relation_reuse={},
        )
    ],
    ids=["build json includes reused audit marker"],
)
def test_given_reused_audit_when_formatting_build_json_then_includes_reused_marker(
    test_case: ExecutionJsonRelationReuseTestCase,
) -> None:
    result: str = format_build_execution_json(
        result=BuildExecutionResult(
            status=BuildStatus.SUCCESS,
            model_results=(
                ModelExecutionResult(
                    model_name="orders",
                    status=ExecutionStatus.SUCCESS,
                    promoted_relation="dev.orders",
                    audit_results=(
                        build_audit_result(
                            name="orders_id_not_null",
                            outcome=AuditOutcome.PASS,
                            target_name="orders",
                            reused=True,
                        ),
                    ),
                ),
            ),
        ),
        plan=build_plan_output(model_entries=(build_model_entry(name="orders"),)),
    )
    payload: dict[str, object] = json.loads(result)
    assets: list[dict[str, object]] = payload["assets"]  # type: ignore[assignment]
    checks: list[dict[str, object]] = payload["checks"]  # type: ignore[assignment]

    assert assets[0]["name"] == test_case.expected_asset_name
    assert checks[0]["reused"] is True


@pytest.mark.parametrize(
    "test_case",
    [
        ExecutionJsonSeedReasonTestCase(
            description="build json includes seed reason",
            expected_asset_name="order_amounts",
            expected_reason="config_changed",
        )
    ],
    ids=["build json includes seed reason"],
)
def test_given_seed_result_when_formatting_build_json_then_includes_seed_reason(
    test_case: ExecutionJsonSeedReasonTestCase,
) -> None:
    result: str = format_build_execution_json(
        result=BuildExecutionResult(
            status=BuildStatus.SUCCESS,
            seed_results=(
                SeedExecutionResult(
                    seed_name="order_amounts",
                    status=ExecutionStatus.SUCCESS,
                ),
            ),
        ),
        plan=build_plan_output(
            seed_entries=(
                build_seed_entry(name="order_amounts", reason=PlanReason.CONFIG_CHANGED),
            ),
        ),
    )
    payload: dict[str, object] = json.loads(result)
    assets: list[dict[str, object]] = payload["assets"]  # type: ignore[assignment]

    assert assets[0]["name"] == test_case.expected_asset_name
    assert assets[0]["reason"] == test_case.expected_reason
