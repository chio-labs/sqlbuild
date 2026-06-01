"""Tests for execution JSON serialization."""

from __future__ import annotations

import json

import pytest

from sqlbuild.cli.commands.main.shared.helpers.execution_json import format_build_execution_json
from sqlbuild.compiler.python_nodes.types import PythonNodeKind, PythonNodeStatus
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.python_nodes.models import PythonNodeExecutionResult
from tests.unit.src.sqlbuild.cli.commands.main.plan.helpers.helpers import build_plan_output
from tests.unit.src.sqlbuild.cli.commands.main.shared.helpers._test_types import (
    ExecutionJsonTestCase,
)


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
