"""Execution-result document entries read back from the native formatters."""

from __future__ import annotations

import json
from typing import cast

from sqlbuild._native import (
    format_audit_execution_json,
    format_build_execution_json,
    format_test_execution_json,
)
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.testing.models import SqlTestExecutionResult, StepResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from tests.unit.src.sqlbuild.cli.output.main.plan.helpers import build_plan_output


def formatted_model_asset(result: ModelExecutionResult) -> dict[str, object]:
    """Return the build document asset of one model result."""

    document: dict[str, object] = json.loads(
        format_build_execution_json(
            result=BuildExecutionResult(status=BuildStatus.SUCCESS, model_results=(result,)),
            plan=build_plan_output(),
        )
    )
    return cast(list[dict[str, object]], document["assets"])[0]


def formatted_audit_check(result: AuditExecutionResult) -> dict[str, object]:
    """Return the audit document check of one audit result."""

    document: dict[str, object] = json.loads(format_audit_execution_json(results=(result,)))
    return cast(list[dict[str, object]], document["checks"])[0]


def formatted_sql_test_check(result: SqlTestExecutionResult) -> dict[str, object]:
    """Return the test document check of one SQL test result."""

    document: dict[str, object] = json.loads(format_test_execution_json(results=(result,)))
    return cast(list[dict[str, object]], document["checks"])[0]


def formatted_sql_test_step(step: StepResult) -> dict[str, object]:
    """Return the test document entry of one SQL test step."""

    check: dict[str, object] = formatted_sql_test_check(
        SqlTestExecutionResult(
            test_name="orders_test", outcome=SqlTestOutcome.FAIL, step_results=(step,)
        )
    )
    return cast(list[dict[str, object]], check["steps"])[0]
