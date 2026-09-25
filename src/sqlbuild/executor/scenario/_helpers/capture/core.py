"""Helpers for running scenario snapshot capture steps."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import ScenarioExecutionPlan
from sqlbuild.executor.build.models import SeedExecutionResult
from sqlbuild.executor.scenario._helpers.lifecycle.failures import first_failure_details
from sqlbuild.executor.scenario._helpers.lifecycle.fixtures import (
    execute_scenario_fixtures,
    execute_scenario_seed_entries,
)
from sqlbuild.executor.scenario._helpers.snapshots.core import (
    build_scenario_snapshot_capture_plan,
    build_scenario_snapshot_manifest_shell,
)
from sqlbuild.executor.scenario.constants import SCENARIO_EXEC_CLEANUP_FAILED
from sqlbuild.executor.scenario.main._capture import execute_scenario_snapshot_capture
from sqlbuild.executor.scenario.main._cleanup import execute_scenario_cleanup
from sqlbuild.executor.scenario.models import (
    ScenarioCaptureSettings,
    ScenarioCleanupExecutionResult,
    ScenarioFailureDetails,
    ScenarioFixtureExecutionResult,
    ScenarioSnapshotCapturePlan,
    ScenarioSnapshotCaptureResult,
    ScenarioSnapshotCaptureRunResult,
    ScenarioSnapshotManifest,
)
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle
from sqlbuild.runtime.observability.main.run_scope import run_scope

_CAPTURE_FAILED_MESSAGE: str = "scenario snapshot capture failed"


def execute_scenario_snapshot_capture_steps(
    *,
    project_dir: Path,
    scenario_plan: ScenarioExecutionPlan,
    adapter: BaseAdapter,
    connection: Any,
    run_id: str,
    settings: ScenarioCaptureSettings,
    local_type_overrides: dict[str, str] | None = None,
) -> ScenarioSnapshotCaptureRunResult:
    """Materialize scenario inputs, capture JSONL snapshots, and apply cleanup policy."""

    with run_scope(run_id):
        with OperationLifecycle(
            operation_kind="scenario", operation_name="scenario_capture"
        ) as lifecycle:
            result: ScenarioSnapshotCaptureRunResult = _execute_scenario_snapshot_capture_steps(
                project_dir=project_dir,
                scenario_plan=scenario_plan,
                adapter=adapter,
                connection=connection,
                run_id=run_id,
                settings=settings,
                local_type_overrides=local_type_overrides,
            )
            if result.status == ExecutionStatus.FAILED:
                lifecycle.failed(error_code=result.error_code)
            return result


def _execute_scenario_snapshot_capture_steps(
    *,
    project_dir: Path,
    scenario_plan: ScenarioExecutionPlan,
    adapter: BaseAdapter,
    connection: Any,
    run_id: str,
    settings: ScenarioCaptureSettings,
    local_type_overrides: dict[str, str] | None,
) -> ScenarioSnapshotCaptureRunResult:

    prepare_result: ScenarioCleanupExecutionResult = execute_scenario_cleanup(
        scenario_plan=scenario_plan,
        adapter=adapter,
        connection=connection,
    )
    if prepare_result.status == ExecutionStatus.FAILED:
        return ScenarioSnapshotCaptureRunResult(
            scenario_name=scenario_plan.name,
            status=ExecutionStatus.FAILED,
            retained=settings.retain,
            prepare_cleanup_result=prepare_result,
            error_code=prepare_result.error_code,
            error_help=prepare_result.error_help,
            error_message=prepare_result.error_message,
        )

    fixture_results: tuple[ScenarioFixtureExecutionResult, ...] = execute_scenario_fixtures(
        scenario_name=scenario_plan.name,
        fixture_plans=scenario_plan.fixture_plans,
        adapter=adapter,
        connection=connection,
    )
    fixture_failure: ScenarioFailureDetails = first_failure_details(
        results=fixture_results, fallback_message=_CAPTURE_FAILED_MESSAGE
    )
    if fixture_failure.error_message is not None:
        return _finish_capture_run(
            scenario_plan=scenario_plan,
            adapter=adapter,
            connection=connection,
            retain=settings.retain,
            prepare_cleanup_result=prepare_result,
            fixture_results=fixture_results,
            failure=fixture_failure,
        )

    seed_results: tuple[SeedExecutionResult, ...] = execute_scenario_seed_entries(
        scenario_name=scenario_plan.name,
        seed_entries=scenario_plan.seed_entries,
        adapter=adapter,
        connection=connection,
        run_id=run_id,
    )
    seed_failure: ScenarioFailureDetails = first_failure_details(
        results=seed_results, fallback_message=_CAPTURE_FAILED_MESSAGE
    )
    if seed_failure.error_message is not None:
        return _finish_capture_run(
            scenario_plan=scenario_plan,
            adapter=adapter,
            connection=connection,
            retain=settings.retain,
            prepare_cleanup_result=prepare_result,
            fixture_results=fixture_results,
            seed_results=seed_results,
            failure=seed_failure,
        )

    capture_plan: ScenarioSnapshotCapturePlan = build_scenario_snapshot_capture_plan(
        project_dir=project_dir,
        scenario_plan=scenario_plan,
        capture_adapter=settings.capture_adapter,
        capture_dialect=settings.capture_dialect,
    )
    manifest: ScenarioSnapshotManifest = build_scenario_snapshot_manifest_shell(
        capture_plan=capture_plan,
        captured_at=settings.captured_at,
        capture_adapter=settings.capture_adapter,
        capture_dialect=settings.capture_dialect,
        sqlbuild_version=settings.sqlbuild_version,
    )
    capture_result: ScenarioSnapshotCaptureResult = execute_scenario_snapshot_capture(
        capture_plan=capture_plan,
        manifest=manifest,
        adapter=adapter,
        connection=connection,
        local_type_overrides=local_type_overrides,
        limits=settings.limits,
    )

    return _finish_capture_run(
        scenario_plan=scenario_plan,
        adapter=adapter,
        connection=connection,
        retain=settings.retain,
        prepare_cleanup_result=prepare_result,
        fixture_results=fixture_results,
        seed_results=seed_results,
        capture_result=capture_result,
        failure=ScenarioFailureDetails(
            error_code=capture_result.error_code,
            error_help=capture_result.error_help,
            error_message=capture_result.error_message,
        ),
    )


def _finish_capture_run(
    *,
    scenario_plan: ScenarioExecutionPlan,
    adapter: BaseAdapter,
    connection: Any,
    retain: bool,
    prepare_cleanup_result: ScenarioCleanupExecutionResult,
    fixture_results: tuple[ScenarioFixtureExecutionResult, ...] = (),
    seed_results: tuple[SeedExecutionResult, ...] = (),
    capture_result: ScenarioSnapshotCaptureResult | None = None,
    failure: ScenarioFailureDetails | None = None,
) -> ScenarioSnapshotCaptureRunResult:
    resolved_failure: ScenarioFailureDetails = (
        failure if failure is not None else ScenarioFailureDetails()
    )
    error_code: str | None = resolved_failure.error_code
    error_help: str | None = resolved_failure.error_help
    error_message: str | None = resolved_failure.error_message
    status: ExecutionStatus = (
        ExecutionStatus.FAILED if error_message is not None else ExecutionStatus.SUCCESS
    )
    cleanup_result: ScenarioCleanupExecutionResult | None = None
    if not retain:
        cleanup_result = execute_scenario_cleanup(
            scenario_plan=scenario_plan,
            adapter=adapter,
            connection=connection,
        )
        if cleanup_result.status == ExecutionStatus.FAILED:
            status = ExecutionStatus.FAILED
            if error_code is None:
                error_code = cleanup_result.error_code or SCENARIO_EXEC_CLEANUP_FAILED
                error_help = cleanup_result.error_help
            cleanup_error: str = cleanup_result.error_message or "scenario cleanup failed"
            if error_message is None:
                error_message = f"Cleanup failed: {cleanup_error}"
            else:
                error_message = f"{error_message}\nCleanup failed: {cleanup_error}"

    return ScenarioSnapshotCaptureRunResult(
        scenario_name=scenario_plan.name,
        status=status,
        retained=retain,
        fixture_results=fixture_results,
        seed_results=seed_results,
        capture_result=capture_result,
        prepare_cleanup_result=prepare_cleanup_result,
        cleanup_result=cleanup_result,
        error_code=error_code,
        error_help=error_help,
        error_message=error_message,
    )
