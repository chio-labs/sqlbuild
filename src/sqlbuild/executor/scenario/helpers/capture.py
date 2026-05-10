"""Helpers for running scenario snapshot capture steps."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import ScenarioExecutionPlan
from sqlbuild.executor.build.models import SeedExecutionResult
from sqlbuild.executor.scenario.helpers.fixtures import (
    execute_scenario_fixtures,
    execute_scenario_seed_entries,
)
from sqlbuild.executor.scenario.helpers.snapshots import (
    build_scenario_snapshot_capture_plan,
    build_scenario_snapshot_manifest_shell,
)
from sqlbuild.executor.scenario.main.capture import execute_scenario_snapshot_capture
from sqlbuild.executor.scenario.main.cleanup import execute_scenario_cleanup
from sqlbuild.executor.scenario.models import (
    ScenarioCleanupExecutionResult,
    ScenarioFixtureExecutionResult,
    ScenarioSnapshotCaptureLimits,
    ScenarioSnapshotCapturePlan,
    ScenarioSnapshotCaptureResult,
    ScenarioSnapshotCaptureRunResult,
    ScenarioSnapshotManifest,
)
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.shared.constants import SCENARIO_EXEC_CLEANUP_FAILED


def execute_scenario_snapshot_capture_steps(
    *,
    project_dir: Path,
    scenario_plan: ScenarioExecutionPlan,
    adapter: BaseAdapter,
    connection: Any,
    captured_at: str,
    capture_adapter: str,
    capture_dialect: str,
    sqlbuild_version: str,
    retain: bool,
    local_type_overrides: dict[str, str] | None = None,
    limits: ScenarioSnapshotCaptureLimits | None = None,
) -> ScenarioSnapshotCaptureRunResult:
    """Materialize scenario inputs, capture JSONL snapshots, and apply cleanup policy."""

    prepare_result: ScenarioCleanupExecutionResult = execute_scenario_cleanup(
        scenario_plan=scenario_plan,
        adapter=adapter,
        connection=connection,
    )
    if prepare_result.status == ExecutionStatus.FAILED:
        return ScenarioSnapshotCaptureRunResult(
            scenario_name=scenario_plan.name,
            status=ExecutionStatus.FAILED,
            retained=retain,
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
    fixture_error: str | None = _first_error(fixture_results)
    if fixture_error is not None:
        return _finish_capture_run(
            scenario_plan=scenario_plan,
            adapter=adapter,
            connection=connection,
            retain=retain,
            prepare_cleanup_result=prepare_result,
            fixture_results=fixture_results,
            error_code=_first_error_code(fixture_results),
            error_help=_first_error_help(fixture_results),
            error_message=fixture_error,
        )

    seed_results: tuple[SeedExecutionResult, ...] = execute_scenario_seed_entries(
        seed_entries=scenario_plan.seed_entries,
        adapter=adapter,
        connection=connection,
    )
    seed_error: str | None = _first_error(seed_results)
    if seed_error is not None:
        return _finish_capture_run(
            scenario_plan=scenario_plan,
            adapter=adapter,
            connection=connection,
            retain=retain,
            prepare_cleanup_result=prepare_result,
            fixture_results=fixture_results,
            seed_results=seed_results,
            error_code=_first_error_code(seed_results),
            error_help=_first_error_help(seed_results),
            error_message=seed_error,
        )

    capture_plan: ScenarioSnapshotCapturePlan = build_scenario_snapshot_capture_plan(
        project_dir=project_dir,
        scenario_plan=scenario_plan,
        capture_adapter=capture_adapter,
        capture_dialect=capture_dialect,
    )
    manifest: ScenarioSnapshotManifest = build_scenario_snapshot_manifest_shell(
        capture_plan=capture_plan,
        captured_at=captured_at,
        capture_adapter=capture_adapter,
        capture_dialect=capture_dialect,
        sqlbuild_version=sqlbuild_version,
    )
    capture_result: ScenarioSnapshotCaptureResult = execute_scenario_snapshot_capture(
        capture_plan=capture_plan,
        manifest=manifest,
        adapter=adapter,
        connection=connection,
        local_type_overrides=local_type_overrides,
        limits=limits,
    )

    return _finish_capture_run(
        scenario_plan=scenario_plan,
        adapter=adapter,
        connection=connection,
        retain=retain,
        prepare_cleanup_result=prepare_result,
        fixture_results=fixture_results,
        seed_results=seed_results,
        capture_result=capture_result,
        error_code=capture_result.error_code,
        error_help=capture_result.error_help,
        error_message=capture_result.error_message,
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
    error_code: str | None = None,
    error_help: str | None = None,
    error_message: str | None = None,
) -> ScenarioSnapshotCaptureRunResult:
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


def _first_error(results: tuple[object, ...]) -> str | None:
    result: object
    for result in results:
        if getattr(result, "status", None) == ExecutionStatus.FAILED:
            return str(getattr(result, "error_message", "scenario snapshot capture failed"))
    return None


def _first_error_code(results: tuple[object, ...]) -> str | None:
    result: object
    for result in results:
        if getattr(result, "status", None) == ExecutionStatus.FAILED:
            error_code: object | None = getattr(result, "error_code", None)
            if isinstance(error_code, str) and error_code:
                return error_code
    return None


def _first_error_help(results: tuple[object, ...]) -> str | None:
    result: object
    for result in results:
        if getattr(result, "status", None) == ExecutionStatus.FAILED:
            error_help: object | None = getattr(result, "error_help", None)
            if isinstance(error_help, str) and error_help:
                return error_help
    return None
