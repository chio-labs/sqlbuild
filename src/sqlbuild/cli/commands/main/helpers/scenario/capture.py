"""Scenario snapshot capture command runner."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.helpers.scenario.constants import SUCCESS_STATUS
from sqlbuild.cli.commands.main.helpers.scenario.selection import select_scenarios
from sqlbuild.cli.commands.main.helpers.scenario.snapshot_limits import (
    build_scenario_snapshot_capture_limits,
    scenario_snapshot_capture_warning,
)
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_project_connection_config
from sqlbuild.cli.commands.main.shared.helpers.connection_progress import ConnectionProgressReporter
from sqlbuild.cli.commands.main.shared.helpers.planning_progress import PlanningProgressReporter
from sqlbuild.cli.commands.main.shared.helpers.progress import format_build_header
from sqlbuild.cli.commands.main.shared.helpers.status import TransientStatusReporter
from sqlbuild.compiler.compile.models import CompiledSqlScenario
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import ScenarioExecutionPlan
from sqlbuild.executor.build.models import SeedExecutionResult
from sqlbuild.executor.pipeline.main.run import run_scenario_capture_pipeline
from sqlbuild.executor.scenario.models import (
    ScenarioFixtureExecutionResult,
    ScenarioSnapshotCaptureLimits,
    ScenarioSnapshotCaptureRelationResult,
    ScenarioSnapshotCaptureResult,
    ScenarioSnapshotCaptureRunResult,
)
from sqlbuild.shared.helpers.coded_errors import format_coded_error
from sqlbuild.shared.helpers.colors import (
    blue_bold,
    colorize_status,
    dim,
    green_bold,
    supports_color,
)
from sqlbuild.spec.models.project import (
    resolve_effective_adapter_name,
    resolve_effective_scenario_config,
)

_SCENARIO_NAME_WIDTH: int = 64


def run_scenario_capture(
    project_dir: Path | None,
    no_sql_validation: bool = False,
    no_color: bool = False,
    selectors: tuple[str, ...] = (),
    retain: bool = False,
    force: bool = False,
    max_snapshot_rows: int | None = None,
    max_snapshot_total_rows: int | None = None,
    max_snapshot_bytes: int | None = None,
    max_snapshot_total_bytes: int | None = None,
) -> int:
    """Execute the scenario capture command."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(adapter_name, project_dir=effective_project_dir)
    connection_config: dict[str, object] = resolve_project_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=effective_project_dir,
    )
    use_color: bool = not no_color and supports_color()
    progress_stream: TextIO = sys.stdout
    target_label: str | None = " ".join(selectors) if selectors else None
    execution_header: str = format_build_header(
        command="sqb scenario capture", target=target_label, concurrency=1
    )
    execution_label: str = blue_bold("Execution") if use_color else "Execution"
    header_detail: str = dim(execution_header) if use_color else execution_header
    connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        stream=progress_stream,
        use_color=use_color,
    )
    planning_progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=progress_stream,
        use_color=use_color,
    )
    progress_stream.write(f"\n{execution_label}  {header_detail}\n\n")
    progress_stream.write(f"{scenario_snapshot_capture_warning(force=force)}\n\n")
    progress_stream.flush()

    pipeline_result: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        connection_config=connection_config,
        on_connection_start=connection_progress.on_connection_start,
        on_connection_complete=connection_progress.on_connection_complete,
        on_connection_error=connection_progress.on_connection_error,
        on_progress=planning_progress.on_progress,
    )
    scenarios: tuple[CompiledSqlScenario, ...] = select_scenarios(
        project=pipeline_result.project,
        selectors=selectors,
        project_dir=effective_project_dir,
    )
    header: str = f"Scenario Capture ({len(scenarios)} selected)"
    styled_header: str = green_bold(header) if use_color else header
    progress_stream.write(f"\n{styled_header}\n\n")
    progress_stream.flush()
    scenario_status: TransientStatusReporter = TransientStatusReporter(
        stream=progress_stream,
        use_color=use_color,
    )
    execution_connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        stream=progress_stream,
        use_color=use_color,
    )

    status_is_tty: bool = hasattr(progress_stream, "isatty") and progress_stream.isatty()
    if not status_is_tty:
        progress_stream.write("Capturing scenarios...\n\n")
        progress_stream.flush()
    results: tuple[ScenarioSnapshotCaptureRunResult, ...]
    capture_limits: ScenarioSnapshotCaptureLimits = build_scenario_snapshot_capture_limits(
        scenario_config=resolve_effective_scenario_config(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        ),
        max_rows_per_relation=max_snapshot_rows,
        max_total_rows=max_snapshot_total_rows,
        max_bytes_per_relation=max_snapshot_bytes,
        max_total_bytes=max_snapshot_total_bytes,
        force=force,
    )
    results = run_scenario_capture_pipeline(
        project_dir=effective_project_dir,
        pipeline_result=pipeline_result,
        scenarios=scenarios,
        connection_config=connection_config,
        adapter=adapter,
        project_name=discovered_inputs.project_config.name,
        captured_at=_captured_at(),
        capture_adapter=adapter_name,
        capture_dialect=adapter_name,
        sqlbuild_version=_sqlbuild_version(),
        retain=retain,
        capture_limits=capture_limits,
        on_connection_start=execution_connection_progress.on_connection_start,
        on_connection_complete=execution_connection_progress.on_connection_complete,
        on_connection_error=execution_connection_progress.on_connection_error,
        on_scenario_start=lambda _scenario: (
            scenario_status.start("Capturing scenarios...") if status_is_tty else None
        ),
        on_scenario_complete=lambda _scenario, scenario_plan, result: _complete_capture_run(
            scenario_status=scenario_status,
            status_is_tty=status_is_tty,
            scenario_plan=scenario_plan,
            result=result,
            progress_stream=progress_stream,
            use_color=use_color,
        ),
    )
    scenario_status.close()

    pass_count: int = sum(1 for result in results if result.status == SUCCESS_STATUS)
    fail_count: int = len(results) - pass_count
    progress_stream.write(f"\nPASS={pass_count}  FAIL={fail_count}  TOTAL={len(results)}\n")
    progress_stream.flush()
    return 0 if fail_count == 0 else 1


def _complete_capture_run(
    *,
    scenario_status: TransientStatusReporter,
    status_is_tty: bool,
    scenario_plan: ScenarioExecutionPlan | None,
    result: ScenarioSnapshotCaptureRunResult,
    progress_stream: TextIO,
    use_color: bool,
) -> None:
    if status_is_tty:
        scenario_status.close()
    _write_capture_result(
        result=result,
        scenario_plan=scenario_plan,
        stream=progress_stream,
        use_color=use_color,
    )


def _write_capture_result(
    *,
    result: ScenarioSnapshotCaptureRunResult,
    scenario_plan: ScenarioExecutionPlan | None,
    stream: TextIO,
    use_color: bool,
) -> None:
    status_text: str = "PASS" if result.status == SUCCESS_STATUS else "FAIL"
    status: str = colorize_status(status_text, use_color=use_color)
    detail: str = _capture_detail(result)
    stream.write(f"{result.scenario_name:<{_SCENARIO_NAME_WIDTH}} {status}{detail}\n")
    if result.error_message:
        rendered_error_message: str = _render_result_error(
            error_code=result.error_code,
            error_message=result.error_message,
            error_help=result.error_help,
        )
        error_line: str
        for error_line in rendered_error_message.splitlines():
            stream.write(f"    {error_line}\n")
        if not result.retained:
            stream.write("    Rerun with --retain to inspect scenario-owned artifacts.\n")
    if result.capture_result is not None and result.capture_result.manifest_path is not None:
        stream.write(f"    snapshot {result.capture_result.manifest_path}\n")
    if result.retained and scenario_plan is not None:
        stream.write("    Retained relations:\n")
        fixture_result: ScenarioFixtureExecutionResult
        for fixture_result in result.fixture_results:
            stream.write(
                f"      {fixture_result.kind.value:<6} "
                f"{fixture_result.logical_name} -> {fixture_result.target_relation}\n"
            )
        seed_result: SeedExecutionResult
        for seed_result in result.seed_results:
            stream.write(f"      seed   {seed_result.seed_name}\n")
    stream.flush()


def _capture_detail(result: ScenarioSnapshotCaptureRunResult) -> str:
    capture_result: ScenarioSnapshotCaptureResult | None = result.capture_result
    if capture_result is None:
        return ""
    relation_results: tuple[ScenarioSnapshotCaptureRelationResult, ...] = (
        capture_result.relation_results
    )
    relation_count: int = sum(
        1 for relation in relation_results if relation.status == SUCCESS_STATUS
    )
    row_count: int = sum(relation.row_count for relation in relation_results)
    relation_label: str = "relation" if relation_count == 1 else "relations"
    row_label: str = "row" if row_count == 1 else "rows"
    return f"  {relation_count} {relation_label}, {row_count} {row_label}"


def _render_result_error(
    *, error_code: str | None, error_message: str, error_help: str | None = None
) -> str:
    if error_code is None:
        return error_message
    return format_coded_error(code=error_code, message=error_message, help=error_help)


def _captured_at() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sqlbuild_version() -> str:
    try:
        return version("sqlbuild")
    except PackageNotFoundError:
        return "unknown"
