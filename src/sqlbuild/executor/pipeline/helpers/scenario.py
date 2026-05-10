"""Scenario test execution pipeline."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledSqlScenario
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.main.scenario import build_scenario_plan
from sqlbuild.compiler.planner.models import ScenarioExecutionPlan
from sqlbuild.executor.scenario.main.capture_steps import execute_scenario_snapshot_capture_run
from sqlbuild.executor.scenario.main.local import execute_local_scenario_load_only_run
from sqlbuild.executor.scenario.main.run import execute_scenario_run
from sqlbuild.executor.scenario.models import ScenarioRunResult, ScenarioSnapshotCaptureRunResult
from sqlbuild.executor.scenario.types import ScenarioLocalRunStatus
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.shared.constants import (
    SCENARIO_EXEC_INTERNAL,
    SCENARIO_LOCAL_INTERNAL,
)
from sqlbuild.shared.helpers.coded_errors import error_code, error_help, error_message
from sqlbuild.spec.models.project import scenario_local_type_overrides_for_dialect


def run_scenario_test_pipeline(
    *,
    pipeline_result: CompilePipelineResult,
    scenarios: tuple[CompiledSqlScenario, ...],
    connection_config: dict[str, object],
    adapter: BaseAdapter,
    project_name: str,
    retain: bool,
    on_connection_start: Callable[[int], None] | None = None,
    on_connection_complete: Callable[[int, float], None] | None = None,
    on_connection_error: Callable[[int, float], None] | None = None,
    on_scenario_start: Callable[[CompiledSqlScenario], None] | None = None,
    on_scenario_complete: Callable[
        [CompiledSqlScenario, ScenarioExecutionPlan | None, ScenarioRunResult], None
    ]
    | None = None,
) -> tuple[ScenarioRunResult, ...]:
    """Execute selected scenarios from a compiled project."""

    if on_connection_start is not None:
        on_connection_start(1)
    start: float = time.monotonic()
    try:
        connection: Any = adapter.connect(connection_config)
    except Exception:
        if on_connection_error is not None:
            on_connection_error(1, time.monotonic() - start)
        raise
    if on_connection_complete is not None:
        on_connection_complete(1, time.monotonic() - start)
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
                    error_code=error_code(exc, fallback_code=SCENARIO_EXEC_INTERNAL),
                    error_help=error_help(exc)
                    or (
                        "This is likely a SQLBuild bug. Please file an issue with the "
                        "scenario name."
                    ),
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
            )
        except Exception as exc:
            result = ScenarioRunResult(
                scenario_name=scenario.name,
                status=ExecutionStatus.FAILED,
                local_status=ScenarioLocalRunStatus.ERROR,
                retained=False,
                error_code=error_code(exc, fallback_code=SCENARIO_LOCAL_INTERNAL),
                error_help=error_help(exc)
                or ("This is likely a SQLBuild bug. Please file an issue with the scenario name."),
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
    captured_at: str,
    capture_adapter: str,
    capture_dialect: str,
    sqlbuild_version: str,
    retain: bool,
    on_connection_start: Callable[[int], None] | None = None,
    on_connection_complete: Callable[[int, float], None] | None = None,
    on_connection_error: Callable[[int, float], None] | None = None,
    on_scenario_start: Callable[[CompiledSqlScenario], None] | None = None,
    on_scenario_complete: Callable[
        [CompiledSqlScenario, ScenarioExecutionPlan | None, ScenarioSnapshotCaptureRunResult], None
    ]
    | None = None,
) -> tuple[ScenarioSnapshotCaptureRunResult, ...]:
    """Capture selected scenario inputs into durable local snapshot files."""

    if on_connection_start is not None:
        on_connection_start(1)
    start: float = time.monotonic()
    try:
        connection: Any = adapter.connect(connection_config)
    except Exception:
        if on_connection_error is not None:
            on_connection_error(1, time.monotonic() - start)
        raise
    if on_connection_complete is not None:
        on_connection_complete(1, time.monotonic() - start)
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
                    captured_at=captured_at,
                    capture_adapter=capture_adapter,
                    capture_dialect=capture_dialect,
                    sqlbuild_version=sqlbuild_version,
                    retain=retain,
                    local_type_overrides=scenario_local_type_overrides_for_dialect(
                        scenario_config=pipeline_result.project.scenario,
                        sqlglot_dialect=adapter.sqlglot_dialect(),
                    ),
                )
            except Exception as exc:
                result = ScenarioSnapshotCaptureRunResult(
                    scenario_name=scenario.name,
                    status=ExecutionStatus.FAILED,
                    retained=retain,
                    error_code=error_code(exc, fallback_code=SCENARIO_EXEC_INTERNAL),
                    error_help=error_help(exc)
                    or (
                        "This is likely a SQLBuild bug. Please file an issue with the "
                        "scenario name."
                    ),
                    error_message=error_message(exc),
                )
            results.append(result)
            if on_scenario_complete is not None:
                on_scenario_complete(scenario, scenario_plan, result)
        return tuple(results)
    finally:
        adapter.close(connection)
