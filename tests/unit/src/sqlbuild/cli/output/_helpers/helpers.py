"""Execution-result document entries read back from the native formatters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from sqlbuild._native import (
    ExecutionEventWriter,
    IntegrationResultEnvelope,
    TerminalEventIndex,
    audit_resource_id,
    format_audit_execution_json,
    format_build_execution_json,
    format_test_execution_json,
    terminal_event_index_scope,
)
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.testing.models import SqlTestExecutionResult, StepResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from sqlbuild.runtime.observability.models import LifecycleEvent
from tests.unit.src.sqlbuild.cli.output.main.plan.helpers import build_plan_output
from tests.unit.src.sqlbuild.runtime.observability.helpers import lifecycle_event


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


def written_integration_record(
    *, result: object, terminal: LifecycleEvent, directory: Path, command: str = "build"
) -> IntegrationResultEnvelope:
    """Write the integration record of one result after its terminal and decode it."""

    path: Path = directory / "integration.jsonl"
    index: TerminalEventIndex = TerminalEventIndex()
    index.consume(terminal)
    with terminal_event_index_scope(index):
        writer: ExecutionEventWriter = ExecutionEventWriter(path=path)
        writer.write_build_result(result=result, plan=None, command=command)
        writer.close()
    return IntegrationResultEnvelope.from_json(path.read_text(encoding="utf-8"))


def audit_terminal(result: AuditExecutionResult) -> LifecycleEvent:
    """Return the completed terminal of one audit result."""

    return lifecycle_event(
        "resource_attempt_completed",
        run_id="run-1",
        resource_id=audit_resource_id(
            audit_name=result.audit_name,
            attachment_kind=result.attachment_kind,
            attached_target_kind=result.attached_target_kind,
            attached_target_name=result.attached_target_name,
            attached_column_name=result.attached_column_name,
        ),
        resource_attempt_id="attempt-1",
        payload={"resource_kind": "audit", "resource_name": result.audit_name, "attempt_number": 1},
    )
