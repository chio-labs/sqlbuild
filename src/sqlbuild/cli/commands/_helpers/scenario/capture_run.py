"""Shared scenario snapshot capture execution."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.scenario.constants import SUCCESS_STATUS
from sqlbuild.cli.commands._helpers.scenario.models import ScenarioRunOutputContext
from sqlbuild.cli.commands._helpers.scenario.result_output import render_result_error
from sqlbuild.cli.progress.classes.connection_progress_reporter import ConnectionProgressReporter
from sqlbuild.compiler.compile.models import CompiledSqlScenario
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import ScenarioExecutionPlan
from sqlbuild.executor.build.models import SeedExecutionResult
from sqlbuild.executor.pipeline.main.run import run_scenario_capture_pipeline
from sqlbuild.executor.scenario.models import (
    ScenarioCaptureSettings,
    ScenarioFixtureExecutionResult,
    ScenarioSnapshotCaptureLimits,
    ScenarioSnapshotCaptureRelationResult,
    ScenarioSnapshotCaptureResult,
    ScenarioSnapshotCaptureRunResult,
)
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.classes.transient_status_reporter import TransientStatusReporter
from sqlbuild.presentation.main.summary_footer import format_summary_footer
from sqlbuild.runtime.contracts.models import ConnectionHooks

_SCENARIO_NAME_WIDTH: int = 64
_CAPTURE_RELATION_KIND_WIDTH: int = 8
_CAPTURE_RELATION_NAME_WIDTH: int = _SCENARIO_NAME_WIDTH - 4 - _CAPTURE_RELATION_KIND_WIDTH - 1


def run_scenario_capture_run(
    *,
    project_dir: Path,
    pipeline_result: CompilePipelineResult,
    scenarios: tuple[CompiledSqlScenario, ...],
    connection_config: dict[str, object],
    adapter: BaseAdapter,
    adapter_name: str,
    project_name: str,
    settings: ScenarioCaptureSettings,
    output_context: ScenarioRunOutputContext,
    capture_results_out: list[ScenarioSnapshotCaptureRunResult] | None = None,
) -> tuple[int, list[ScenarioSnapshotCaptureRunResult] | None]:
    """Capture selected scenarios to durable snapshots and render results."""

    progress_stream: TextIO = output_context.progress_stream
    use_color: bool = output_context.use_color
    style: CliStyle = CliStyle(use_color=use_color)
    header: str = f"Scenario Capture ({len(scenarios)} selected)"
    progress_stream.write(f"\n{style.success_strong(header)}\n\n")
    progress_stream.flush()
    scenario_status: TransientStatusReporter = TransientStatusReporter(
        stream=progress_stream,
        use_color=use_color,
    )
    execution_connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        blank_line_after_complete=True,
        stream=progress_stream,
        use_color=use_color,
    )
    status_is_tty: bool = hasattr(progress_stream, "isatty") and progress_stream.isatty()
    if not status_is_tty:
        progress_stream.write("Capturing scenarios...\n\n")
        progress_stream.flush()
    results: tuple[ScenarioSnapshotCaptureRunResult, ...] = run_scenario_capture_pipeline(
        project_dir=project_dir,
        pipeline_result=pipeline_result,
        scenarios=scenarios,
        connection_config=connection_config,
        adapter=adapter,
        project_name=project_name,
        settings=settings,
        connection_hooks=ConnectionHooks(
            on_connection_start=execution_connection_progress.on_connection_start,
            on_connection_complete=lambda connection_count, elapsed_seconds: (
                execution_connection_progress.on_connection_complete(
                    connection_count=connection_count, elapsed_seconds=elapsed_seconds
                )
            ),
            on_connection_error=lambda connection_count, elapsed_seconds: (
                execution_connection_progress.on_connection_error(
                    connection_count=connection_count, elapsed_seconds=elapsed_seconds
                )
            ),
        ),
        on_scenario_start=lambda _scenario: (
            scenario_status.start("Capturing scenarios...") if status_is_tty else None
        ),
        on_scenario_complete=lambda _scenario, scenario_plan, result: _complete_capture_run(
            scenario_status=scenario_status,
            status_is_tty=status_is_tty,
            project_dir=project_dir,
            scenario_plan=scenario_plan,
            result=result,
            progress_stream=progress_stream,
            use_color=use_color,
        ),
    )
    scenario_status.close()
    if capture_results_out is not None:
        capture_results_out.extend(results)
    pass_count: int = sum(1 for result in results if result.status == SUCCESS_STATUS)
    fail_count: int = len(results) - pass_count
    progress_stream.write(
        "\n"
        + format_summary_footer(
            counts=(
                ("PASS", pass_count),
                ("FAIL", fail_count),
                ("TOTAL", len(results)),
            ),
            use_color=use_color,
        )
        + "\n"
    )
    progress_stream.flush()
    return (0 if fail_count == 0 else 1), capture_results_out


def _complete_capture_run(
    *,
    scenario_status: TransientStatusReporter,
    status_is_tty: bool,
    project_dir: Path,
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
        project_dir=project_dir,
        stream=progress_stream,
        use_color=use_color,
    )


def _write_capture_result(
    *,
    result: ScenarioSnapshotCaptureRunResult,
    scenario_plan: ScenarioExecutionPlan | None,
    project_dir: Path,
    stream: TextIO,
    use_color: bool,
) -> None:
    status_text: str = "PASS" if result.status == SUCCESS_STATUS else "FAIL"
    style: CliStyle = CliStyle(use_color=use_color)
    status: str = style.status(status=status_text)
    detail: str = _capture_detail(result)
    stream.write(f"{result.scenario_name:<{_SCENARIO_NAME_WIDTH}} {status}{detail}\n")
    if result.error_message:
        rendered_error_message: str = render_result_error(
            error_code=result.error_code,
            error_message=result.error_message,
            error_help=result.error_help,
            use_color=use_color,
        )
        error_line: str
        for error_line in rendered_error_message.splitlines():
            stream.write(f"    {error_line}\n")
        if not result.retained:
            stream.write("    Rerun with --retain to inspect scenario-owned artifacts.\n")
    if result.capture_result is not None and result.capture_result.manifest_path is not None:
        _write_capture_relation_rows(result=result, stream=stream, use_color=use_color)
        snapshot_path: str = _display_snapshot_path(
            manifest_path=result.capture_result.manifest_path,
            project_dir=project_dir,
        )
        stream.write(f"    {'snapshot':<{_CAPTURE_RELATION_KIND_WIDTH}} {snapshot_path}\n")
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


def _write_capture_relation_rows(
    *, result: ScenarioSnapshotCaptureRunResult, stream: TextIO, use_color: bool
) -> None:
    capture_result: ScenarioSnapshotCaptureResult | None = result.capture_result
    if capture_result is None:
        return
    relation_result: ScenarioSnapshotCaptureRelationResult
    for relation_result in capture_result.relation_results:
        status_text: str = "PASS" if relation_result.status == SUCCESS_STATUS else "FAIL"
        style: CliStyle = CliStyle(use_color=use_color)
        status: str = style.status(status=status_text)
        row_label: str = "row" if relation_result.row_count == 1 else "rows"
        detail: str = (
            f"  {relation_result.row_count} {row_label}, "
            f"{_format_snapshot_size(relation_result.byte_count)}"
        )
        stream.write(
            f"    {relation_result.kind.value:<{_CAPTURE_RELATION_KIND_WIDTH}} "
            f"{relation_result.logical_name:<{_CAPTURE_RELATION_NAME_WIDTH}} "
            f"{status}{detail}\n"
        )


def _format_snapshot_size(byte_count: int) -> str:
    binary_unit_size: int = 1024
    if byte_count < binary_unit_size:
        return f"{byte_count} B"
    kibibytes: float = byte_count / 1024
    if kibibytes < binary_unit_size:
        return f"{kibibytes:.1f} KB"
    mebibytes: float = kibibytes / 1024
    return f"{mebibytes:.1f} MB"


def _display_snapshot_path(*, manifest_path: Path, project_dir: Path) -> str:
    try:
        return manifest_path.relative_to(project_dir).as_posix()
    except ValueError:
        return manifest_path.as_posix()


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


def build_scenario_capture_settings(
    *,
    capture_adapter: str,
    capture_dialect: str,
    retain: bool,
    limits: ScenarioSnapshotCaptureLimits,
) -> ScenarioCaptureSettings:
    """Build capture settings with current provenance for a scenario capture run."""

    return ScenarioCaptureSettings(
        captured_at=_captured_at(),
        capture_adapter=capture_adapter,
        capture_dialect=capture_dialect,
        sqlbuild_version=_sqlbuild_version(),
        retain=retain,
        limits=limits,
    )


def _captured_at() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sqlbuild_version() -> str:
    try:
        return version("sqlbuild")
    except PackageNotFoundError:
        return "unknown"
