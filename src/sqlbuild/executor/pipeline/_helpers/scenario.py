"""Scenario test execution pipeline."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledSqlScenario
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.main.scenarios.scenario import build_scenario_plan
from sqlbuild.compiler.planner.models import ScenarioExecutionPlan
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event
from sqlbuild.errors.contracts.main.error_code import error_code
from sqlbuild.errors.contracts.main.error_help import error_help
from sqlbuild.errors.contracts.main.error_message import error_message
from sqlbuild.executor.scenario.constants import (
    SCENARIO_EXEC_INTERNAL,
    SCENARIO_LOCAL_INTERNAL,
)
from sqlbuild.executor.scenario.main._capture_steps import (
    execute_scenario_snapshot_capture_run,
)
from sqlbuild.executor.scenario.main._local import execute_local_scenario_load_only_run
from sqlbuild.executor.scenario.main._run import execute_scenario_run
from sqlbuild.executor.scenario.main._snapshots import classify_scenario_snapshot_state
from sqlbuild.executor.scenario.models import (
    ScenarioCaptureSettings,
    ScenarioRunResult,
    ScenarioSnapshotCaptureRunResult,
    ScenarioSnapshotStateResult,
)
from sqlbuild.executor.scenario.types import ScenarioLocalRunStatus, ScenarioSnapshotState
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.runtime.contracts.models import ConnectionHooks
from sqlbuild.spec.contracts.main.scenario_local_type_overrides_for_dialect import (
    scenario_local_type_overrides_for_dialect,
)

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.execution")
_SCENARIO_INTERNAL_ERROR_HELP: str = (
    "This is likely a SQLBuild bug. Please file an issue with the scenario name."
)


def _scenario_failure_help(exc: Exception) -> str | None:
    explicit_help: str | None = error_help(exc)
    if explicit_help is not None:
        return explicit_help
    if getattr(exc, "code", None) is not None:
        return None
    return _SCENARIO_INTERNAL_ERROR_HELP


def run_scenario_test_pipeline(
    *,
    pipeline_result: CompilePipelineResult,
    scenarios: tuple[CompiledSqlScenario, ...],
    connection_config: dict[str, object],
    adapter: BaseAdapter,
    project_name: str,
    retain: bool,
    connection_hooks: ConnectionHooks | None = None,
    on_scenario_start: Callable[[CompiledSqlScenario], None] | None = None,
    on_scenario_complete: Callable[
        [CompiledSqlScenario, ScenarioExecutionPlan | None, ScenarioRunResult], None
    ]
    | None = None,
) -> tuple[ScenarioRunResult, ...]:
    """Execute selected scenarios from a compiled project."""

    hooks: ConnectionHooks = connection_hooks if connection_hooks is not None else ConnectionHooks()
    if hooks.on_connection_start is not None:
        hooks.on_connection_start(1)
    start: float = time.monotonic()
    try:
        connection: Any = adapter.connect(connection_config)
    except Exception:
        if hooks.on_connection_error is not None:
            hooks.on_connection_error(1, elapsed_seconds=time.monotonic() - start)
        raise
    if hooks.on_connection_complete is not None:
        hooks.on_connection_complete(1, elapsed_seconds=time.monotonic() - start)
    try:
        results: list[ScenarioRunResult] = []
        scenario: CompiledSqlScenario
        for scenario in scenarios:
            if on_scenario_start is not None:
                on_scenario_start(scenario)
            scenario_plan: ScenarioExecutionPlan | None = None
            try:
                scenario_plan = build_scenario_plan(
                    scenario=scenario,
                    pipeline_result=pipeline_result,
                    adapter=adapter,
                    project_name=project_name,
                )
                result: ScenarioRunResult = execute_scenario_run(
                    scenario_plan=scenario_plan,
                    adapter=adapter,
                    connection=connection,
                    run_id=pipeline_result.project.run_id,
                    retain=retain,
                )
            except Exception as exc:
                result = ScenarioRunResult(
                    scenario_name=scenario.name,
                    status=ExecutionStatus.FAILED,
                    retained=retain,
                    error_code=error_code(error=exc, fallback_code=SCENARIO_EXEC_INTERNAL),
                    error_help=_scenario_failure_help(exc),
                    error_message=error_message(exc),
                )
            results.append(result)
            if on_scenario_complete is not None:
                on_scenario_complete(scenario, scenario_plan, result)
        return tuple(results)
    finally:
        adapter.close(connection)


def run_scenario_local_test_pipeline(
    *,
    project_dir: Path,
    pipeline_result: CompilePipelineResult,
    scenarios: tuple[CompiledSqlScenario, ...],
    adapter: BaseAdapter,
    project_name: str,
    strict: bool,
    capture_adapter: str | None = None,
    capture_dialect: str | None = None,
    on_scenario_start: Callable[[CompiledSqlScenario], None] | None = None,
    on_scenario_complete: Callable[
        [CompiledSqlScenario, ScenarioExecutionPlan | None, ScenarioRunResult], None
    ]
    | None = None,
) -> tuple[ScenarioRunResult, ...]:
    """Load selected local scenario snapshots into run-scoped DuckDB databases."""

    results: list[ScenarioRunResult] = []
    scenario: CompiledSqlScenario
    for scenario in scenarios:
        if on_scenario_start is not None:
            on_scenario_start(scenario)
        scenario_plan: ScenarioExecutionPlan | None = None
        try:
            scenario_plan = build_scenario_plan(
                scenario=scenario,
                pipeline_result=pipeline_result,
                adapter=adapter,
                project_name=project_name,
            )
            result: ScenarioRunResult = execute_local_scenario_load_only_run(
                project_dir=project_dir,
                scenario_plan=scenario_plan,
                adapter=adapter,
                strict=strict,
                capture_adapter=capture_adapter,
                capture_dialect=capture_dialect,
            )
        except Exception as exc:
            result = ScenarioRunResult(
                scenario_name=scenario.name,
                status=ExecutionStatus.FAILED,
                local_status=ScenarioLocalRunStatus.ERROR,
                retained=False,
                error_code=error_code(error=exc, fallback_code=SCENARIO_LOCAL_INTERNAL),
                error_help=_scenario_failure_help(exc),
                error_message=error_message(exc),
            )
        results.append(result)
        if on_scenario_complete is not None:
            on_scenario_complete(scenario, scenario_plan, result)
    return tuple(results)


def run_scenario_capture_pipeline(
    *,
    project_dir: Path,
    pipeline_result: CompilePipelineResult,
    scenarios: tuple[CompiledSqlScenario, ...],
    connection_config: dict[str, object],
    adapter: BaseAdapter,
    project_name: str,
    settings: ScenarioCaptureSettings,
    connection_hooks: ConnectionHooks | None = None,
    on_scenario_start: Callable[[CompiledSqlScenario], None] | None = None,
    on_scenario_complete: Callable[
        [CompiledSqlScenario, ScenarioExecutionPlan | None, ScenarioSnapshotCaptureRunResult], None
    ]
    | None = None,
) -> tuple[ScenarioSnapshotCaptureRunResult, ...]:
    """Capture selected scenario inputs into durable local snapshot files."""

    hooks: ConnectionHooks = connection_hooks if connection_hooks is not None else ConnectionHooks()
    if hooks.on_connection_start is not None:
        hooks.on_connection_start(1)
    start: float = time.monotonic()
    try:
        connection: Any = adapter.connect(connection_config)
    except Exception:
        if hooks.on_connection_error is not None:
            hooks.on_connection_error(1, elapsed_seconds=time.monotonic() - start)
        raise
    if hooks.on_connection_complete is not None:
        hooks.on_connection_complete(1, elapsed_seconds=time.monotonic() - start)
    try:
        results: list[ScenarioSnapshotCaptureRunResult] = []
        scenario: CompiledSqlScenario
        for scenario in scenarios:
            if on_scenario_start is not None:
                on_scenario_start(scenario)
            scenario_plan: ScenarioExecutionPlan | None = None
            try:
                scenario_plan = build_scenario_plan(
                    scenario=scenario,
                    pipeline_result=pipeline_result,
                    adapter=adapter,
                    project_name=project_name,
                )
                result: ScenarioSnapshotCaptureRunResult = execute_scenario_snapshot_capture_run(
                    project_dir=project_dir,
                    scenario_plan=scenario_plan,
                    adapter=adapter,
                    connection=connection,
                    settings=settings,
                    local_type_overrides=scenario_local_type_overrides_for_dialect(
                        scenario_config=pipeline_result.project.scenario,
                        sql_analysis_dialect=adapter.sql_analysis_dialect(),
                    ),
                )
            except Exception as exc:
                result = ScenarioSnapshotCaptureRunResult(
                    scenario_name=scenario.name,
                    status=ExecutionStatus.FAILED,
                    retained=settings.retain,
                    error_code=error_code(error=exc, fallback_code=SCENARIO_EXEC_INTERNAL),
                    error_help=_scenario_failure_help(exc),
                    error_message=error_message(exc),
                )
            results.append(result)
            if on_scenario_complete is not None:
                on_scenario_complete(scenario, scenario_plan, result)
        return tuple(results)
    finally:
        adapter.close(connection)


def select_scenario_snapshot_capture_candidates(
    *,
    project_dir: Path,
    pipeline_result: CompilePipelineResult,
    scenarios: tuple[CompiledSqlScenario, ...],
    adapter: BaseAdapter,
    project_name: str,
    capture_adapter: str,
    capture_dialect: str,
    refresh: bool,
) -> tuple[str, ...]:
    """Return selected scenario names that need snapshot capture before local replay."""

    names: list[str] = []
    scenario: CompiledSqlScenario
    for scenario in scenarios:
        if refresh:
            names.append(scenario.name)
            continue
        try:
            scenario_plan: ScenarioExecutionPlan = build_scenario_plan(
                scenario=scenario,
                pipeline_result=pipeline_result,
                adapter=adapter,
                project_name=project_name,
            )
            snapshot_state: ScenarioSnapshotStateResult = classify_scenario_snapshot_state(
                project_dir=project_dir,
                scenario_plan=scenario_plan,
                capture_adapter=capture_adapter,
                capture_dialect=capture_dialect,
            )
        except Exception as error:
            log_debug_event(
                logger=_DEBUG_LOGGER,
                message="scenario snapshot state classification failed; skipping auto-capture",
                scenario=scenario.name,
                sqlbuild_error=str(error),
            )
            continue
        if snapshot_state.state in (ScenarioSnapshotState.MISSING, ScenarioSnapshotState.STALE):
            names.append(scenario.name)
    return tuple(names)
