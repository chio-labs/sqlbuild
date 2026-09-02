"""Version 1 structured JSON output protocol for execution commands."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from pathlib import Path
from typing import cast

from sqlbuild.cli.output._helpers.future_cursor_safety import serialize_future_cursor_safety
from sqlbuild.cli.output.classes.terminal_event_index import (
    TerminalEventIndex,
    current_terminal_event_index,
)
from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import (
    PlanOutput,
)
from sqlbuild.compiler.python_nodes.types import PythonNodeStatus
from sqlbuild.executor.auditing.main.resource_id import audit_resource_id
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build.main.aggregate_result import aggregate_build_result
from sqlbuild.executor.build.models import (
    BuildExecutionResult,
    FunctionExecutionResult,
    SeedExecutionResult,
)
from sqlbuild.executor.build.types import BuildStatus, ExecutionStatus
from sqlbuild.executor.clone.models import CloneExecutionResult, CloneItemResult
from sqlbuild.executor.clone.types import CloneStatus
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.python_nodes.models import (
    PythonCheckExecutionResult,
    PythonNodeExecutionResult,
)
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.scenario.models import (
    ScenarioAssertionExpectationExecutionResult,
    ScenarioExpectedExpectationExecutionResult,
    ScenarioRunResult,
    ScenarioSnapshotCaptureRelationResult,
    ScenarioSnapshotCaptureRunResult,
)
from sqlbuild.executor.scenario.types import ScenarioLocalRunStatus
from sqlbuild.executor.testing.models import SqlTestExecutionResult, StepResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from sqlbuild.runtime.observability.models import LifecycleEvent
from sqlbuild.sql_values.models import SqlValue
from sqlbuild.sql_values.types import SqlValueKind
from sqlbuild.virtual.executor.constants import (
    VIRTUAL_CLONE_FOUND_ACTIONS,
    VIRTUAL_CLONE_MISSING_ACTION,
    VIRTUAL_CLONE_SKIPPED_LOCKED_ACTION,
)
from sqlbuild.virtual.executor.models import VirtualCloneResult

_JSON_VERSION: int = 1
_SUCCESS_STATUS: str = "success"
_FAILED_STATUS: str = "failed"
_SKIPPED_STATUS: str = "skipped"
_WARNING_STATUS: str = "warning"
_WARN_STATUS: str = "warn"
_SCENARIO_RESOURCE_NAMESPACE: ContextVar[str | None] = ContextVar(
    "sqlbuild_scenario_resource_namespace", default=None
)


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


def format_build_execution_json(
    *,
    result: BuildExecutionResult,
    plan: PlanOutput,
    python_node_results: tuple[PythonNodeExecutionResult, ...] = (),
    python_check_results: tuple[PythonCheckExecutionResult, ...] = (),
    command: str = "build",
    run_id: str | None = None,
    cost: dict[str, object] | None = None,
) -> str:
    """Format build command execution results as JSON."""

    python_node_result_count: int = len(python_node_results)
    python_check_result_count: int = len(python_check_results)
    model_results: tuple[ModelExecutionResult, ...] = _terminal_results(
        results=result.model_results
    )
    seed_results: tuple[SeedExecutionResult, ...] = _terminal_results(results=result.seed_results)
    function_results: tuple[FunctionExecutionResult, ...] = _terminal_results(
        results=result.function_results
    )
    load_results: tuple[LoadExecutionResult, ...] = _terminal_results(results=result.load_results)
    test_results: tuple[SqlTestExecutionResult, ...] = _terminal_results(
        results=result.test_results
    )
    source_audit_results: tuple[AuditExecutionResult, ...] = _terminal_results(
        results=result.source_audit_results
    )
    end_audit_results: tuple[AuditExecutionResult, ...] = _terminal_results(
        results=result.end_audit_results
    )
    python_node_results = _terminal_results(results=python_node_results)
    python_check_results = _terminal_results(results=python_check_results)
    python_fail_count: int = _python_node_result_count(
        results=python_node_results, status=PythonNodeStatus.FAILED
    )
    python_success_count: int = _python_node_result_count(
        results=python_node_results, status=PythonNodeStatus.SUCCESS
    )
    python_skipped_count: int = _python_node_result_count(
        results=python_node_results, status=PythonNodeStatus.SKIPPED
    )
    python_check_fail_count: int = sum(1 for result in python_check_results if result.failed)
    python_check_warn_count: int = sum(1 for result in python_check_results if result.warned)
    python_check_pass_count: int = sum(1 for result in python_check_results if result.passed)
    status: BuildStatus = (
        BuildStatus.FAILED
        if result.status == BuildStatus.FAILED or python_fail_count or python_check_fail_count
        else result.status
    )
    retained_result: BuildExecutionResult = aggregate_build_result(
        model_results=model_results,
        seed_results=seed_results,
        function_results=function_results,
        load_results=load_results,
        test_results=test_results,
        source_audit_results=source_audit_results,
        end_audit_results=end_audit_results,
    )
    checks: list[dict[str, object]] = []
    checks.extend(_format_sql_test_checks(test_results))
    checks.extend(_format_audit_checks(results=source_audit_results))
    checks.extend(_format_audit_checks(results=end_audit_results))
    for model_result in model_results:
        checks.extend(
            _format_audit_checks(
                results=model_result.audit_results,
                terminal_evidence=_result_has_terminal(result=model_result),
            )
        )
    checks.extend(_format_python_check_results(results=python_check_results))
    assets: tuple[dict[str, object], ...] = (
        *_format_model_assets(results=model_results, plan=plan),
        *_format_seed_assets(results=seed_results, plan=plan),
        *_format_function_assets(results=function_results, plan=plan),
        *_format_load_assets(results=load_results),
        *_format_python_node_assets(results=python_node_results),
    )
    summary: dict[str, object] = {
        "success_count": result.success_count + python_success_count,
        "failure_count": result.failure_count + python_fail_count + python_check_fail_count,
        "skipped_count": result.skipped_count + python_skipped_count,
        "warning_count": result.warning_count + python_check_warn_count,
        "python_check_pass_count": python_check_pass_count,
        "python_check_warn_count": python_check_warn_count,
        "python_check_fail_count": python_check_fail_count,
    }
    if (
        _build_projection_is_partial(
            result=result,
            model_results=model_results,
            seed_results=seed_results,
            function_results=function_results,
            load_results=load_results,
            test_results=test_results,
            source_audit_results=source_audit_results,
            end_audit_results=end_audit_results,
        )
        or len(python_node_results) != python_node_result_count
        or len(python_check_results) != python_check_result_count
    ):
        summary = {
            "success_count": retained_result.success_count + python_success_count,
            "failure_count": (
                retained_result.failure_count + python_fail_count + python_check_fail_count
            ),
            "skipped_count": retained_result.skipped_count + python_skipped_count,
            "warning_count": retained_result.warning_count + python_check_warn_count,
            "python_check_pass_count": python_check_pass_count,
            "python_check_warn_count": python_check_warn_count,
            "python_check_fail_count": python_check_fail_count,
        }
    return _format_execution_json(
        command=command,
        status=status.value,
        assets=assets,
        checks=tuple(checks),
        summary=summary,
        run_id=run_id,
        cost=cost,
    )


def format_run_execution_json(
    *,
    result: BuildExecutionResult,
    plan: PlanOutput,
    python_node_results: tuple[PythonNodeExecutionResult, ...] = (),
) -> str:
    """Format run command execution results as JSON."""

    python_node_result_count: int = len(python_node_results)
    model_results: tuple[ModelExecutionResult, ...] = _terminal_results(
        results=result.model_results
    )
    seed_results: tuple[SeedExecutionResult, ...] = _terminal_results(results=result.seed_results)
    function_results: tuple[FunctionExecutionResult, ...] = _terminal_results(
        results=result.function_results
    )
    load_results: tuple[LoadExecutionResult, ...] = _terminal_results(results=result.load_results)
    python_node_results = _terminal_results(results=python_node_results)
    python_fail_count: int = _python_node_result_count(
        results=python_node_results, status=PythonNodeStatus.FAILED
    )
    python_success_count: int = _python_node_result_count(
        results=python_node_results, status=PythonNodeStatus.SUCCESS
    )
    python_skipped_count: int = _python_node_result_count(
        results=python_node_results, status=PythonNodeStatus.SKIPPED
    )
    status: BuildStatus = (
        BuildStatus.FAILED
        if result.status == BuildStatus.FAILED or python_fail_count
        else result.status
    )
    retained_result: BuildExecutionResult = aggregate_build_result(
        model_results=model_results,
        seed_results=seed_results,
        function_results=function_results,
        load_results=load_results,
        test_results=(),
        source_audit_results=(),
        end_audit_results=(),
    )
    assets: tuple[dict[str, object], ...] = (
        *_format_model_assets(results=model_results, plan=plan),
        *_format_seed_assets(results=seed_results, plan=plan),
        *_format_function_assets(results=function_results, plan=plan),
        *_format_load_assets(results=load_results),
        *_format_python_node_assets(results=python_node_results),
    )
    partial: bool = any(
        (
            len(model_results) != len(result.model_results),
            len(seed_results) != len(result.seed_results),
            len(function_results) != len(result.function_results),
            len(load_results) != len(result.load_results),
            len(python_node_results) != python_node_result_count,
        )
    )
    summary: dict[str, object] = {
        "success_count": result.success_count + python_success_count,
        "failure_count": result.failure_count + python_fail_count,
        "skipped_count": result.skipped_count + python_skipped_count,
        "warning_count": result.warning_count,
    }
    if partial:
        summary = {
            "success_count": retained_result.success_count + python_success_count,
            "failure_count": retained_result.failure_count + python_fail_count,
            "skipped_count": retained_result.skipped_count + python_skipped_count,
            "warning_count": retained_result.warning_count,
        }
    return _format_execution_json(
        command="run",
        status=status.value,
        assets=assets,
        checks=(),
        summary=summary,
    )


def format_seed_execution_json(
    *, results: tuple[SeedExecutionResult, ...], plan: PlanOutput
) -> str:
    """Format seed command execution results as JSON."""

    results = _terminal_results(results=results)
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


def format_load_execution_json(*, results: tuple[LoadExecutionResult, ...]) -> str:
    """Format load command execution results as JSON."""

    results = _terminal_results(results=results)
    fail_count: int = sum(1 for result in results if result.status == ExecutionStatus.FAILED)
    return _format_execution_json(
        command="load",
        status=BuildStatus.SUCCESS.value if fail_count == 0 else BuildStatus.FAILED.value,
        assets=_format_load_assets(results=results),
        checks=(),
        summary={
            "success_count": sum(
                1 for result in results if result.status == ExecutionStatus.SUCCESS
            ),
            "failure_count": fail_count,
            "skipped_count": sum(
                1 for result in results if result.status == ExecutionStatus.SKIPPED
            ),
            "total_count": len(results),
        },
    )


def format_clone_execution_json(
    *, result: CloneExecutionResult, resource_types_by_name: Mapping[str, str]
) -> str:
    """Format direct clone command execution results as JSON."""

    item_results: tuple[CloneItemResult, ...] = tuple(
        item
        for item in result.item_results
        if _resource_has_terminal(
            resource_name=item.name,
            resource_id=f"{resource_types_by_name[item.name]}:{item.name}",
        )
    )
    failure_count: int = sum(1 for item in item_results if item.status == CloneStatus.FAILED)
    warning_count: int = sum(1 for item in item_results if item.status == CloneStatus.WARNING)
    return _format_execution_json(
        command="clone",
        status=BuildStatus.SUCCESS.value if failure_count == 0 else BuildStatus.FAILED.value,
        assets=tuple(
            _format_clone_asset(item=item, resource_type=resource_types_by_name[item.name])
            for item in item_results
        ),
        checks=(),
        summary={
            "success_count": len(item_results) - failure_count - warning_count,
            "failure_count": failure_count,
            "warning_count": warning_count,
            "total_count": len(item_results),
        },
    )


def _format_clone_asset(*, item: CloneItemResult, resource_type: str) -> dict[str, object]:
    canonical_duration: float | None = _resource_duration(
        resource_name=item.name,
        resource_id=f"{resource_type}:{item.name}",
        fallback=(item.duration_seconds * 1000 if item.duration_seconds is not None else None),
    )
    return _drop_none(
        {
            "kind": resource_type,
            "name": item.name,
            "status": item.status.value,
            "action": item.action.value,
            "duration_ms": round(canonical_duration) if canonical_duration is not None else None,
            "origin_relation": item.origin_relation,
            "target": item.destination_relation,
            "message": item.message,
        }
    )


def format_virtual_clone_execution_json(*, result: VirtualCloneResult) -> str:
    """Format virtual clone command execution results as JSON."""

    return _format_execution_json(
        command="clone",
        status=(
            BuildStatus.SUCCESS.value if result.missing_count == 0 else BuildStatus.FAILED.value
        ),
        assets=tuple(
            _drop_none(
                {
                    "kind": item.artifact_type.value,
                    "name": item.artifact_name,
                    "status": _virtual_clone_item_status(action=item.action),
                    "action": item.action,
                    "version_hash": item.version_hash,
                    "message": item.message,
                }
            )
            for item in result.item_results
        ),
        checks=(),
        summary={
            "success_count": result.found_count,
            "failure_count": result.missing_count,
            "skipped_count": result.skipped_locked_count,
            "total_count": result.selected_count,
        },
    )


def _virtual_clone_item_status(*, action: str) -> str:
    if action in VIRTUAL_CLONE_FOUND_ACTIONS:
        return "success"
    if action == VIRTUAL_CLONE_SKIPPED_LOCKED_ACTION:
        return "skipped"
    if action == VIRTUAL_CLONE_MISSING_ACTION:
        return "warning"
    return "failed"


def format_test_execution_json(*, results: tuple[SqlTestExecutionResult, ...]) -> str:
    """Format test command execution results as JSON."""

    results = _terminal_results(results=results)
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

    results = _terminal_results(results=results)
    fail_count: int = sum(1 for result in results if result.outcome == AuditOutcome.ERROR)
    return _format_execution_json(
        command="audit",
        status=BuildStatus.SUCCESS.value if fail_count == 0 else BuildStatus.FAILED.value,
        assets=(),
        checks=_format_audit_checks(results=results),
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

    results = tuple(result for result in results if _scenario_result_has_terminal(result=result))
    fail_count: int = sum(1 for result in results if _scenario_failed(result=result, local=local))
    assets: list[dict[str, object]] = []
    checks: list[dict[str, object]] = []
    for result in results:
        with _scenario_resource_namespace(result.scenario_name):
            assets.extend(_format_seed_assets(results=result.seed_results, plan=None))
            assets.extend(_format_function_assets(results=result.function_results, plan=None))
            assets.extend(_format_model_assets(results=result.model_results, plan=None))
        checks.extend(_format_scenario_checks(result))
    return _format_execution_json(
        command="scenario test",
        status=BuildStatus.SUCCESS.value if fail_count == 0 else BuildStatus.FAILED.value,
        assets=tuple(assets),
        checks=tuple(checks),
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
    run_id: str | None = None,
    cost: dict[str, object] | None = None,
) -> str:
    projector: TerminalEventIndex | None = current_terminal_event_index()
    terminal: LifecycleEvent | None = None if projector is None else projector.lifecycle_terminal()
    if terminal is not None:
        status = "failed" if terminal.event_type.endswith("failed") else status
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
    if run_id is not None:
        payload["run_id"] = run_id
    if cost is not None:
        payload["cost"] = cost
    return json.dumps(payload, indent=2) + "\n"


def _python_node_result_count(
    *, results: tuple[PythonNodeExecutionResult, ...], status: PythonNodeStatus
) -> int:
    return sum(1 for python_result in results if python_result.status == status)


def _build_projection_is_partial(
    *,
    result: BuildExecutionResult,
    model_results: tuple[ModelExecutionResult, ...],
    seed_results: tuple[SeedExecutionResult, ...],
    function_results: tuple[FunctionExecutionResult, ...],
    load_results: tuple[LoadExecutionResult, ...],
    test_results: tuple[SqlTestExecutionResult, ...],
    source_audit_results: tuple[AuditExecutionResult, ...],
    end_audit_results: tuple[AuditExecutionResult, ...],
) -> bool:
    return any(
        (
            len(model_results) != len(result.model_results),
            len(seed_results) != len(result.seed_results),
            len(function_results) != len(result.function_results),
            len(load_results) != len(result.load_results),
            len(test_results) != len(result.test_results),
            len(source_audit_results) != len(result.source_audit_results),
            len(end_audit_results) != len(result.end_audit_results),
        )
    )


def _projected_asset_summary(*, assets: tuple[dict[str, object], ...]) -> dict[str, int]:
    return {
        "success_count": sum(1 for asset in assets if asset.get("status") == _SUCCESS_STATUS),
        "failure_count": sum(1 for asset in assets if asset.get("status") == _FAILED_STATUS),
        "skipped_count": sum(1 for asset in assets if asset.get("status") == _SKIPPED_STATUS),
        "warning_count": sum(1 for asset in assets if asset.get("status") == _WARNING_STATUS),
    }


def _format_model_assets(
    *, results: tuple[ModelExecutionResult, ...], plan: PlanOutput | None
) -> tuple[dict[str, object], ...]:
    targets: dict[str, str | None] = {}
    if plan is not None:
        targets = {name: target.qualified_name for name, target in plan.model_locations.items()}
    return tuple(
        _drop_none(
            {
                "kind": CompiledResourceType.MODEL.value,
                "name": result.model_name,
                "status": result.status.value,
                "duration_ms": _result_duration(result=result, fallback=result.duration_ms),
                "target": targets.get(result.model_name) or result.promoted_relation,
                "staging_relation": result.staging_relation,
                "failed_phase": result.failed_phase.value if result.failed_phase else None,
                "skip_mode": result.skip_mode.value if result.skip_mode else None,
                "skip_reason": result.skip_reason,
                "error_code": result.error_code,
                "error_help": result.error_help,
                "error_message": result.error_message,
                "warnings": result.warning_messages,
                "future_cursor_safety": serialize_future_cursor_safety(result.future_cursor_safety),
                "microbatch": _format_microbatch_result(result),
            }
        )
        for result in results
        if _result_has_terminal(result=result)
    )


def _format_microbatch_result(result: ModelExecutionResult) -> dict[str, object] | None:
    if result.microbatch_run_type is None:
        return None
    microbatch: dict[str, object] = {
        "run_type": result.microbatch_run_type,
        "batch_count": result.batch_count,
        "batch_size": result.batch_size,
        "recovery_batch_count": result.microbatch_recovery_batch_count,
        "known_gap_count": result.microbatch_known_gap_count,
        "unaccounted_interval_count": result.microbatch_unaccounted_interval_count,
        "synthetic_completion_count": result.microbatch_synthetic_completion_count,
        "unknown_fingerprint_count": result.microbatch_unknown_fingerprint_count,
        "contiguous_frontier": result.microbatch_contiguous_frontier,
        "unaccounted_partition_policy": result.microbatch_unaccounted_partition_policy,
        "replay_requirement_id": result.microbatch_replay_requirement_id,
        "required_model_version_hash": result.microbatch_required_model_version_hash,
        "physical_generation_id": result.microbatch_physical_generation_id,
        "concurrent_enabled": result.microbatch_concurrent_enabled,
        "batch_concurrency": result.microbatch_batch_concurrency,
        "global_concurrency": result.microbatch_global_concurrency,
        "replay_requirement_state": result.microbatch_replay_requirement_state,
        "intervals": [
            {
                "partition_start": interval.partition_start,
                "partition_end": interval.partition_end,
                "accounting_status": interval.accounting_status,
                "fingerprint_status": interval.fingerprint_status,
                "model_version_hash": interval.model_version_hash,
                "completion_type": interval.completion_type,
                "event_id": interval.event_id,
            }
            for interval in result.microbatch_accounting_intervals
        ],
    }
    if result.microbatch_limit is not None:
        microbatch.update(
            {
                "limit": result.microbatch_limit,
                "count": result.microbatch_limit_count,
                "action": (
                    result.microbatch_limit_action.value
                    if result.microbatch_limit_action is not None
                    else None
                ),
                "warning": result.microbatch_limit_warning,
            }
        )
    return microbatch


def _format_seed_assets(
    *, results: tuple[SeedExecutionResult, ...], plan: PlanOutput | None
) -> tuple[dict[str, object], ...]:
    targets: dict[str, str | None] = {}
    reasons: dict[str, str] = {}
    if plan is not None:
        targets = {name: target.qualified_name for name, target in plan.seed_locations.items()}
        reasons = {entry.name: entry.reason.value for entry in plan.seed_entries}
    return tuple(
        _drop_none(
            {
                "kind": CompiledResourceType.SEED.value,
                "name": result.seed_name,
                "status": result.status.value,
                "duration_ms": _result_duration(result=result, fallback=result.duration_ms),
                "target": targets.get(result.seed_name),
                "reason": reasons.get(result.seed_name),
                "error_code": result.error_code,
                "error_help": result.error_help,
                "error_message": result.error_message,
            }
        )
        for result in results
        if _result_has_terminal(result=result)
    )


def _format_load_assets(
    *, results: tuple[LoadExecutionResult, ...]
) -> tuple[dict[str, object], ...]:
    return tuple(
        _drop_none(
            {
                "kind": result.resource_kind.value,
                "name": result.source_name,
                "status": result.status.value,
                "duration_ms": _result_duration(result=result, fallback=result.duration_ms),
                "target": result.target,
                "staging_relation": result.staging_relation,
                "loader": result.loader_name,
                "rows_loaded": result.rows_loaded,
                "skip_mode": result.skip_mode.value if result.skip_mode else None,
                "skip_reason": result.skip_reason,
                "error_message": result.error_message,
            }
        )
        for result in results
        if _result_has_terminal(result=result)
    )


def _format_python_node_assets(
    *, results: tuple[PythonNodeExecutionResult, ...]
) -> tuple[dict[str, object], ...]:
    return tuple(
        _drop_none(
            {
                "kind": result.kind.value,
                "name": result.node_name,
                "status": result.status.value,
                "metadata": result.metadata,
                "materialized": result.materialized,
                "skip_mode": result.skip_mode.value if result.skip_mode else None,
                "skip_reason": result.skip_reason,
                "error_message": result.error_message,
            }
        )
        for result in results
        if _result_has_terminal(result=result)
    )


def _format_function_assets(
    *, results: tuple[FunctionExecutionResult, ...], plan: PlanOutput | None
) -> tuple[dict[str, object], ...]:
    targets: dict[str, str | None] = {}
    if plan is not None:
        targets = {name: target.qualified_name for name, target in plan.function_locations.items()}
    return tuple(
        _drop_none(
            {
                "kind": result.function_kind,
                "name": result.function_name,
                "status": result.status.value,
                "duration_ms": _result_duration(result=result, fallback=result.duration_ms),
                "target": targets.get(result.function_name),
                "error_code": result.error_code,
                "error_help": result.error_help,
                "error_message": result.error_message,
                "warnings": result.warning_messages,
            }
        )
        for result in results
        if _result_has_terminal(result=result)
    )


def _format_sql_test_checks(
    results: tuple[SqlTestExecutionResult, ...],
) -> tuple[dict[str, object], ...]:
    checks: list[dict[str, object]] = []
    for result in results:
        if not _result_has_terminal(result=result):
            continue
        steps: list[dict[str, object]] = []
        for step in result.step_results:
            steps.append(_format_sql_test_step(step))
        checks.append(
            _drop_none(
                {
                    "kind": "sql_test",
                    "name": result.test_name,
                    "check_id": _sql_test_check_id(result),
                    **_sql_test_case_metadata(result),
                    "passed": result.outcome == SqlTestOutcome.PASS,
                    "status": result.outcome.value,
                    "asset_name": _sql_test_asset_name(result),
                    "error_code": result.error_code,
                    "error_help": result.error_help,
                    "error_message": result.error_message,
                    "steps": tuple(steps),
                }
            )
        )
    return tuple(checks)


def _sql_test_check_id(result: SqlTestExecutionResult) -> str:
    if result.case_name is None or result.source_path is None or result.block_index is None:
        return f"sql_test:{result.test_name}"
    return f"sql_test:{result.source_path.as_posix()}:{result.block_index}:{result.case_name}"


def _sql_test_case_metadata(result: SqlTestExecutionResult) -> dict[str, object]:
    if result.case_name is None or result.source_path is None:
        return {}
    parameter_types: dict[str, str] = {
        parameter.name: parameter.value_type.value for parameter in result.parameter_schema
    }
    return {
        "source_path": result.source_path.as_posix(),
        "block_index": result.block_index,
        "parent_name": result.parent_name,
        "case_name": result.case_name,
        "case_index": result.case_index,
        "case_fingerprint": result.case_fingerprint,
        "parameter_schema": tuple(
            {
                "name": parameter.name,
                "type": parameter.value_type.value,
                "nullable": parameter.nullable,
            }
            for parameter in result.parameter_schema
        ),
        "parameters": tuple(
            {
                "name": name,
                "type": parameter_types[name],
                "value": _sql_value_json(value),
            }
            for name, value in result.parameter_values
        ),
    }


def _sql_value_json(value: SqlValue) -> object:
    if value.kind == SqlValueKind.DECIMAL:
        return str(value.value)
    if value.kind in {
        SqlValueKind.STRING,
        SqlValueKind.INTEGER,
        SqlValueKind.BOOLEAN,
        SqlValueKind.FLOAT,
        SqlValueKind.NULL,
    }:
        return value.value
    if value.kind in {SqlValueKind.LIST, SqlValueKind.SET}:
        return [_sql_value_json(item) for item in cast(tuple[SqlValue, ...], value.value)]
    return {
        name: _sql_value_json(item)
        for name, item in cast(tuple[tuple[str, SqlValue], ...], value.value)
    }


def _format_python_check_results(
    *, results: tuple[PythonCheckExecutionResult, ...]
) -> tuple[dict[str, object], ...]:
    return tuple(
        _drop_none(
            {
                "kind": "python_check",
                "name": result.node_name,
                "check_id": f"python_check:{result.node_name}",
                "passed": result.passed,
                "status": "pass" if result.passed else "warn" if result.warned else "fail",
                "severity": result.severity.value,
                "message": result.message,
                "error_message": result.error_message,
                "metadata": result.metadata,
            }
        )
        for result in results
        if _result_has_terminal(result=result)
    )


def _format_sql_test_step(step: StepResult) -> dict[str, object]:
    return _drop_none(
        {
            "model_name": step.model_name,
            "status": step.outcome.value,
            "actual_row_count": step.actual_row_count,
            "expected_row_count": step.expected_row_count,
            "mismatched_row_count": step.mismatched_row_count,
            "error_code": step.error_code,
            "error_help": step.error_help,
            "error_message": step.error_message,
        }
    )


def _sql_test_asset_name(result: SqlTestExecutionResult) -> str | None:
    if not result.step_results:
        return None
    return result.step_results[0].model_name


def _format_audit_checks(
    *,
    results: tuple[AuditExecutionResult, ...],
    terminal_evidence: bool = False,
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
                "reused": result.reused,
            }
        )
        for result in results
        if terminal_evidence or _result_has_terminal(result=result)
    )


def _audit_check_id(result: AuditExecutionResult) -> str:
    return audit_resource_id(
        audit_name=result.audit_name,
        attachment_kind=result.attachment_kind,
        attached_target_name=result.attached_target_name,
        attached_column_name=result.attached_column_name,
    )


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
    result: ScenarioExpectedExpectationExecutionResult,
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
    result: ScenarioAssertionExpectationExecutionResult,
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


def _scenario_result_has_terminal(*, result: ScenarioRunResult) -> bool:
    return _resource_has_terminal(
        resource_name=result.scenario_name,
        resource_id=f"sql_scenario:{result.scenario_name}",
    )


def _drop_none(value: dict[str, object]) -> dict[str, object]:
    return {key: item for key, item in value.items() if item is not None}


def _result_resource_identity(*, result: object) -> tuple[str | None, str | None]:
    resource_name: str | None = None
    resource_id: str | None = None
    if isinstance(result, ModelExecutionResult):
        resource_name = result.model_name
        resource_id = f"model:{result.model_name}"
    elif isinstance(result, SeedExecutionResult):
        resource_name = result.seed_name
        resource_id = f"seed:{result.seed_name}"
    elif isinstance(result, FunctionExecutionResult):
        resource_name = result.function_name
        resource_id = f"{result.function_kind}:{result.function_name}"
    elif isinstance(result, LoadExecutionResult):
        resource_name = result.source_name
        resource_id = f"source:{result.source_name}"
    elif isinstance(result, PythonNodeExecutionResult):
        resource_name = result.node_name
        resource_id = f"{result.kind.value}:{result.node_name}"
    elif isinstance(result, PythonCheckExecutionResult):
        resource_name = result.node_name
        resource_id = f"check:{result.node_name}"
    elif isinstance(result, SqlTestExecutionResult):
        resource_name = result.test_name
        resource_id = f"sql_test:{result.test_name}"
    elif isinstance(result, AuditExecutionResult):
        resource_name = result.audit_name
        resource_id = _audit_check_id(result)
    scenario_name: str | None = _SCENARIO_RESOURCE_NAMESPACE.get()
    if scenario_name is not None and resource_id is not None:
        resource_id = f"scenario:{scenario_name}:{resource_id}"
    return resource_name, resource_id


@contextmanager
def _scenario_resource_namespace(scenario_name: str) -> Iterator[None]:
    token: Token[str | None] = _SCENARIO_RESOURCE_NAMESPACE.set(scenario_name)
    try:
        yield
    finally:
        _SCENARIO_RESOURCE_NAMESPACE.reset(token)


def _result_has_terminal(*, result: object) -> bool:
    resource_name, resource_id = _result_resource_identity(result=result)
    if resource_name is None:
        return current_terminal_event_index() is None
    return _resource_has_terminal(resource_name=resource_name, resource_id=resource_id)


def _terminal_results[RESULT](*, results: tuple[RESULT, ...]) -> tuple[RESULT, ...]:
    return tuple(result for result in results if _result_has_terminal(result=result))


def _resource_has_terminal(*, resource_name: str, resource_id: str | None) -> bool:
    projector: TerminalEventIndex | None = current_terminal_event_index()
    if projector is None:
        return True
    terminal: LifecycleEvent | None = projector.resource_terminal(
        resource_name=resource_name,
        resource_id=resource_id,
    )
    return terminal is not None


def _result_duration(*, result: object, fallback: int | float | None) -> int | float | None:
    resource_name, resource_id = _result_resource_identity(result=result)
    if resource_name is None:
        return fallback
    duration: float | None = _resource_duration(
        resource_name=resource_name,
        resource_id=resource_id,
        fallback=None if fallback is None else float(fallback),
    )
    return round(duration) if duration is not None else None


def _resource_duration(
    *, resource_name: str, resource_id: str | None, fallback: float | None
) -> float | None:
    projector: TerminalEventIndex | None = current_terminal_event_index()
    if projector is None:
        return fallback
    terminal: LifecycleEvent | None = projector.resource_terminal(
        resource_name=resource_name,
        resource_id=resource_id,
    )
    if terminal is None:
        return None
    duration: object = terminal.payload.get("duration_ms")
    return float(duration) if isinstance(duration, int | float) else None
