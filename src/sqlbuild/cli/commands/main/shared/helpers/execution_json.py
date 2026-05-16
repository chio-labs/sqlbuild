"""Structured JSON output for execution commands."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build.models import (
    BuildExecutionResult,
    FunctionExecutionResult,
    SeedExecutionResult,
)
from sqlbuild.executor.build.types import BuildStatus, ExecutionStatus
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.scenario.models import (
    ScenarioAssertionCheckExecutionResult,
    ScenarioExpectedCheckExecutionResult,
    ScenarioRunResult,
    ScenarioSnapshotCaptureRelationResult,
    ScenarioSnapshotCaptureRunResult,
)
from sqlbuild.executor.scenario.types import ScenarioLocalRunStatus
from sqlbuild.executor.testing.models import SqlTestExecutionResult, StepResult
from sqlbuild.executor.testing.types import SqlTestOutcome

_JSON_VERSION: int = 1


def write_execution_json_output(
    *, payload: str, json_output: bool, json_output_path: Path | None
) -> None:
    """Write execution JSON to stdout or a requested side-channel file."""

    if json_output_path is not None:
        json_output_path.parent.mkdir(parents=True, exist_ok=True)
        json_output_path.write_text(payload, encoding="utf-8")
        return
    if json_output:
        sys.stdout.write(payload)
        sys.stdout.flush()


def format_build_execution_json(*, result: BuildExecutionResult, plan: PlanOutput) -> str:
    """Format build command execution results as JSON."""

    return _format_execution_json(
        command="build",
        status=result.status.value,
        assets=(
            *_format_model_assets(results=result.model_results, plan=plan),
            *_format_seed_assets(results=result.seed_results, plan=plan),
            *_format_function_assets(results=result.function_results, plan=plan),
        ),
        checks=(
            *_format_sql_test_checks(result.test_results),
            *_format_audit_checks(result.source_audit_results),
            *_format_audit_checks(result.end_audit_results),
            *(
                check
                for model_result in result.model_results
                for check in _format_audit_checks(model_result.audit_results)
            ),
        ),
        summary={
            "success_count": result.success_count,
            "failure_count": result.failure_count,
            "skipped_count": result.skipped_count,
            "warning_count": result.warning_count,
        },
    )


def format_run_execution_json(*, result: BuildExecutionResult, plan: PlanOutput) -> str:
    """Format run command execution results as JSON."""

    return _format_execution_json(
        command="run",
        status=result.status.value,
        assets=(
            *_format_model_assets(results=result.model_results, plan=plan),
            *_format_seed_assets(results=result.seed_results, plan=plan),
            *_format_function_assets(results=result.function_results, plan=plan),
        ),
        checks=(),
        summary={
            "success_count": result.success_count,
            "failure_count": result.failure_count,
            "skipped_count": result.skipped_count,
            "warning_count": result.warning_count,
        },
    )


def format_seed_execution_json(
    *, results: tuple[SeedExecutionResult, ...], plan: PlanOutput
) -> str:
    """Format seed command execution results as JSON."""

    fail_count: int = sum(1 for result in results if result.status == ExecutionStatus.FAILED)
    return _format_execution_json(
        command="seed",
        status=BuildStatus.SUCCESS.value if fail_count == 0 else BuildStatus.FAILED.value,
        assets=_format_seed_assets(results=results, plan=plan),
        checks=(),
        summary={
            "success_count": sum(
                1 for result in results if result.status == ExecutionStatus.SUCCESS
            ),
            "failure_count": fail_count,
            "total_count": len(results),
        },
    )


def format_test_execution_json(*, results: tuple[SqlTestExecutionResult, ...]) -> str:
    """Format test command execution results as JSON."""

    fail_count: int = sum(1 for result in results if result.outcome != SqlTestOutcome.PASS)
    return _format_execution_json(
        command="test",
        status=BuildStatus.SUCCESS.value if fail_count == 0 else BuildStatus.FAILED.value,
        assets=(),
        checks=_format_sql_test_checks(results),
        summary={
            "pass_count": sum(1 for result in results if result.outcome == SqlTestOutcome.PASS),
            "fail_count": fail_count,
            "total_count": len(results),
        },
    )


def format_audit_execution_json(*, results: tuple[AuditExecutionResult, ...]) -> str:
    """Format audit command execution results as JSON."""

    fail_count: int = sum(1 for result in results if result.outcome == AuditOutcome.ERROR)
    return _format_execution_json(
        command="audit",
        status=BuildStatus.SUCCESS.value if fail_count == 0 else BuildStatus.FAILED.value,
        assets=(),
        checks=_format_audit_checks(results),
        summary={
            "pass_count": sum(1 for result in results if result.outcome == AuditOutcome.PASS),
            "warn_count": sum(1 for result in results if result.outcome == AuditOutcome.WARN),
            "fail_count": fail_count,
            "total_count": len(results),
        },
    )


def format_scenario_execution_json(
    *, results: tuple[ScenarioRunResult, ...], local: bool = False
) -> str:
    """Format scenario test command execution results as JSON."""

    fail_count: int = sum(1 for result in results if _scenario_failed(result=result, local=local))
    return _format_execution_json(
        command="scenario test",
        status=BuildStatus.SUCCESS.value if fail_count == 0 else BuildStatus.FAILED.value,
        assets=tuple(
            asset
            for result in results
            for asset in (
                *_format_seed_assets(results=result.seed_results, plan=None),
                *_format_function_assets(results=result.function_results, plan=None),
                *_format_model_assets(results=result.model_results, plan=None),
            )
        ),
        checks=tuple(check for result in results for check in _format_scenario_checks(result)),
        scenarios=tuple(_format_scenario_result(result) for result in results),
        summary={
            "pass_count": len(results) - fail_count,
            "fail_count": fail_count,
            "total_count": len(results),
        },
    )


def format_scenario_snapshot_execution_json(
    *, results: tuple[ScenarioSnapshotCaptureRunResult, ...], refresh: bool = False
) -> str:
    """Format scenario snapshot sync/refresh execution results as JSON."""

    fail_count: int = sum(1 for result in results if result.status == ExecutionStatus.FAILED)
    return _format_execution_json(
        command="scenario snapshot refresh" if refresh else "scenario snapshot sync",
        status=BuildStatus.SUCCESS.value if fail_count == 0 else BuildStatus.FAILED.value,
        assets=(),
        checks=(),
        scenarios=tuple(_format_snapshot_result(result) for result in results),
        summary={
            "pass_count": len(results) - fail_count,
            "fail_count": fail_count,
            "total_count": len(results),
        },
    )


def _format_execution_json(
    *,
    command: str,
    status: str,
    assets: tuple[dict[str, object], ...],
    checks: tuple[dict[str, object], ...],
    summary: dict[str, object],
    scenarios: tuple[dict[str, object], ...] = (),
) -> str:
    payload: dict[str, object] = {
        "version": _JSON_VERSION,
        "command": command,
        "status": status,
        "summary": summary,
        "assets": assets,
        "checks": checks,
    }
    if scenarios:
        payload["scenarios"] = scenarios
    return json.dumps(payload, indent=2) + "\n"


def _format_model_assets(
    *, results: tuple[ModelExecutionResult, ...], plan: PlanOutput | None
) -> tuple[dict[str, object], ...]:
    targets: dict[str, str | None] = {}
    if plan is not None:
        targets = {name: target.qualified_name for name, target in plan.model_targets.items()}
    return tuple(
        _drop_none(
            {
                "kind": CompiledResourceType.MODEL.value,
                "name": result.model_name,
                "status": result.status.value,
                "duration_ms": result.duration_ms,
                "target": targets.get(result.model_name) or result.promoted_relation,
                "staging_relation": result.staging_relation,
                "failed_phase": result.failed_phase.value if result.failed_phase else None,
                "error_code": result.error_code,
                "error_help": result.error_help,
                "error_message": result.error_message,
                "warnings": result.warning_messages,
            }
        )
        for result in results
    )


def _format_seed_assets(
    *, results: tuple[SeedExecutionResult, ...], plan: PlanOutput | None
) -> tuple[dict[str, object], ...]:
    targets: dict[str, str | None] = {}
    if plan is not None:
        targets = {name: target.qualified_name for name, target in plan.seed_targets.items()}
    return tuple(
        _drop_none(
            {
                "kind": CompiledResourceType.SEED.value,
                "name": result.seed_name,
                "status": result.status.value,
                "duration_ms": result.duration_ms,
                "target": targets.get(result.seed_name),
                "error_code": result.error_code,
                "error_help": result.error_help,
                "error_message": result.error_message,
            }
        )
        for result in results
    )


def _format_function_assets(
    *, results: tuple[FunctionExecutionResult, ...], plan: PlanOutput | None
) -> tuple[dict[str, object], ...]:
    targets: dict[str, str | None] = {}
    if plan is not None:
        targets = {name: target.qualified_name for name, target in plan.function_targets.items()}
    return tuple(
        _drop_none(
            {
                "kind": CompiledResourceType.FUNCTION.value,
                "name": result.function_name,
                "status": result.status.value,
                "duration_ms": result.duration_ms,
                "target": targets.get(result.function_name),
                "error_code": result.error_code,
                "error_help": result.error_help,
                "error_message": result.error_message,
                "warnings": result.warning_messages,
            }
        )
        for result in results
    )


def _format_sql_test_checks(
    results: tuple[SqlTestExecutionResult, ...],
) -> tuple[dict[str, object], ...]:
    return tuple(
        _drop_none(
            {
                "kind": "sql_test",
                "name": result.test_name,
                "check_id": f"sql_test:{result.test_name}",
                "passed": result.outcome == SqlTestOutcome.PASS,
                "status": result.outcome.value,
                "asset_name": _sql_test_asset_name(result),
                "error_message": result.error_message,
                "steps": tuple(_format_sql_test_step(step) for step in result.step_results),
            }
        )
        for result in results
    )


def _format_sql_test_step(step: StepResult) -> dict[str, object]:
    return _drop_none(
        {
            "model_name": step.model_name,
            "status": step.outcome.value,
            "actual_row_count": step.actual_row_count,
            "expected_row_count": step.expected_row_count,
            "mismatched_row_count": step.mismatched_row_count,
            "error_message": step.error_message,
        }
    )


def _sql_test_asset_name(result: SqlTestExecutionResult) -> str | None:
    if not result.step_results:
        return None
    return result.step_results[0].model_name


def _format_audit_checks(
    results: tuple[AuditExecutionResult, ...],
) -> tuple[dict[str, object], ...]:
    return tuple(
        _drop_none(
            {
                "kind": "audit",
                "name": result.audit_name,
                "check_id": _audit_check_id(result),
                "passed": result.outcome == AuditOutcome.PASS,
                "status": result.outcome.value,
                "severity": result.severity.value,
                "row_count": result.row_count,
                "attachment_kind": result.attachment_kind.value,
                "asset_name": result.attached_target_name,
                "attached_column_name": result.attached_column_name,
                "run_scope_phase": result.run_scope_phase.value,
            }
        )
        for result in results
    )


def _audit_check_id(result: AuditExecutionResult) -> str:
    parts: tuple[str | None, ...] = (
        "audit",
        result.audit_name,
        result.attachment_kind.value,
        result.attached_target_name,
        result.attached_column_name,
    )
    return ":".join(part for part in parts if part)


def _format_scenario_checks(result: ScenarioRunResult) -> tuple[dict[str, object], ...]:
    return (
        _drop_none(
            {
                "kind": "scenario",
                "name": result.scenario_name,
                "check_id": f"sql_scenario:{result.scenario_name}",
                "passed": result.status == ExecutionStatus.SUCCESS,
                "status": result.status.value,
                "expected_results": tuple(
                    _format_scenario_expected(expected) for expected in result.expected_results
                ),
                "assertion_results": tuple(
                    _format_scenario_assertion(assertion) for assertion in result.assertion_results
                ),
                "error_code": result.error_code,
                "error_help": result.error_help,
                "error_message": result.error_message,
            }
        ),
    )


def _format_scenario_result(result: ScenarioRunResult) -> dict[str, object]:
    return _drop_none(
        {
            "name": result.scenario_name,
            "status": result.status.value,
            "local_status": result.local_status.value if result.local_status else None,
            "retained": result.retained,
            "local_duckdb_path": (
                str(result.local_duckdb_path) if result.local_duckdb_path else None
            ),
            "error_code": result.error_code,
            "error_help": result.error_help,
            "error_message": result.error_message,
        }
    )


def _format_scenario_expected(
    result: ScenarioExpectedCheckExecutionResult,
) -> dict[str, object]:
    return _drop_none(
        {
            "model_name": result.model_name,
            "status": result.status.value,
            "actual_row_count": result.actual_row_count,
            "expected_row_count": result.expected_row_count,
            "mismatched_row_count": result.mismatched_row_count,
            "error_code": result.error_code,
            "error_help": result.error_help,
            "error_message": result.error_message,
        }
    )


def _format_scenario_assertion(
    result: ScenarioAssertionCheckExecutionResult,
) -> dict[str, object]:
    return _drop_none(
        {
            "name": result.name,
            "status": result.status.value,
            "failing_row_count": result.failing_row_count,
            "sample_rows": result.sample_rows,
            "error_code": result.error_code,
            "error_help": result.error_help,
            "error_message": result.error_message,
        }
    )


def _format_snapshot_result(result: ScenarioSnapshotCaptureRunResult) -> dict[str, object]:
    return _drop_none(
        {
            "name": result.scenario_name,
            "status": result.status.value,
            "retained": result.retained,
            "relations": tuple(
                _format_snapshot_relation(relation)
                for relation in (
                    result.capture_result.relation_results
                    if result.capture_result is not None
                    else ()
                )
            ),
            "manifest_path": str(result.capture_result.manifest_path)
            if result.capture_result is not None
            else None,
            "error_code": result.error_code,
            "error_help": result.error_help,
            "error_message": result.error_message,
        }
    )


def _format_snapshot_relation(
    result: ScenarioSnapshotCaptureRelationResult,
) -> dict[str, object]:
    return _drop_none(
        {
            "kind": result.kind.value,
            "logical_name": result.logical_name,
            "source_relation": result.source_relation,
            "file_path": str(result.file_path),
            "status": result.status.value,
            "row_count": result.row_count,
            "byte_count": result.byte_count,
            "error_code": result.error_code,
            "error_help": result.error_help,
            "error_message": result.error_message,
        }
    )


def _scenario_failed(*, result: ScenarioRunResult, local: bool) -> bool:
    if local:
        return result.local_status in {
            ScenarioLocalRunStatus.FAIL,
            ScenarioLocalRunStatus.ERROR,
        }
    return result.status == ExecutionStatus.FAILED


def _drop_none(value: dict[str, object]) -> dict[str, object]:
    return {key: item for key, item in value.items() if item is not None}
