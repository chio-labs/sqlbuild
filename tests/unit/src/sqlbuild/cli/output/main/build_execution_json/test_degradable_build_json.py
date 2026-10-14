"""Degradable build execution JSON boundary tests."""

from __future__ import annotations

import json

import pytest

from sqlbuild._native import format_degradable_build_execution_json
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from tests.unit.src.sqlbuild.cli.output.main.build_execution_json._test_types import (
    ExecutionJsonAuditDegradationTestCase,
)
from tests.unit.src.sqlbuild.cli.output.main.plan.helpers import build_plan_output


@pytest.mark.parametrize(
    "test_case",
    [
        ExecutionJsonAuditDegradationTestCase(
            description="audit result persistence failure",
            result=BuildExecutionResult(
                status=BuildStatus.SUCCESS,
                audit_result_projection_attempted_count=3,
                audit_result_projection_written_count=0,
                audit_result_projection_failed_count=3,
            ),
            expected_status="success",
            expected_projection={"attempted_count": 3, "written_count": 0, "failed_count": 3},
        )
    ],
    ids=lambda case: case.description,
)
def test_given_audit_history_write_failure_when_formatting_json_then_reports_bounded_degradation(
    test_case: ExecutionJsonAuditDegradationTestCase,
) -> None:
    payload: dict[str, object] = json.loads(
        format_degradable_build_execution_json(
            result=test_case.result,
            plan=build_plan_output(),
            python_node_results=(),
            python_check_results=(),
            command="build",
            run_id="run",
            cost=None,
            execution_succeeded=True,
        )
    )

    assert payload["status"] == test_case.expected_status
    assert payload["projection_degraded"] is True
    assert payload["audit_result_projection"] == test_case.expected_projection
    assert payload["projection_degradation_reasons"] == [
        {"reason": "audit_result_projection_failure", **test_case.expected_projection}
    ]


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
