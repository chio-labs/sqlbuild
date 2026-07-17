"""Shared local DuckDB scenario replay execution."""

from __future__ import annotations

from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.scenario_output.result_output import complete_scenario_run
from sqlbuild.cli.commands.models import ScenarioRunOutputContext
from sqlbuild.cli.output.main._scenario_execution_json import (
    format_scenario_execution_json,
)
from sqlbuild.cli.output.main._write_execution_json_output import write_execution_json_output
from sqlbuild.compiler.compile.models import CompiledSqlScenario
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.executor.pipeline.main.run import run_scenario_local_test_pipeline
from sqlbuild.executor.scenario.models import ScenarioRunResult
from sqlbuild.executor.scenario.types import ScenarioLocalRunStatus
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.classes.transient_status_reporter import TransientStatusReporter
from sqlbuild.presentation.main.summary_footer import format_summary_footer


def run_local_scenarios(
    *,
    project_dir: Path,
    pipeline_result: CompilePipelineResult,
    scenarios: tuple[CompiledSqlScenario, ...],
    adapter: BaseAdapter,
    project_name: str,
    strict: bool,
    capture_adapter: str,
    capture_dialect: str,
    target_dir: Path,
    output_context: ScenarioRunOutputContext,
) -> int:
    """Replay selected scenarios on run-scoped DuckDB and render results."""

    progress_stream: TextIO = output_context.progress_stream
    use_color: bool = output_context.use_color
    json_output: bool = output_context.json_output
    json_output_path: Path | None = output_context.json_output_path
    style: CliStyle = CliStyle(use_color=use_color)
    progress_stream.write(f"\n{style.success_strong(f'Scenario ({len(scenarios)} selected)')}\n\n")
    progress_stream.flush()
    scenario_status: TransientStatusReporter = TransientStatusReporter(
        stream=progress_stream,
        use_color=use_color,
    )
    status_is_tty: bool = hasattr(progress_stream, "isatty") and progress_stream.isatty()
    if not status_is_tty:
        progress_stream.write("Running scenarios...\n\n")
        progress_stream.flush()
    results: tuple[ScenarioRunResult, ...] = run_scenario_local_test_pipeline(
        project_dir=project_dir,
        pipeline_result=pipeline_result,
        scenarios=scenarios,
        adapter=adapter,
        project_name=project_name,
        strict=strict,
        capture_adapter=capture_adapter,
        capture_dialect=capture_dialect,
        on_scenario_start=lambda _scenario: (
            scenario_status.start("Running scenarios...") if status_is_tty else None
        ),
        on_scenario_complete=lambda _scenario, scenario_plan, result: complete_scenario_run(
            scenario_status=scenario_status,
            status_is_tty=status_is_tty,
            target_dir=target_dir,
            adapter=adapter,
            scenario_plan=scenario_plan,
            result=result,
            progress_stream=progress_stream,
            use_color=use_color,
        ),
    )
    scenario_status.close()
    exit_code: int = _write_local_summary(
        results=results, stream=progress_stream, use_color=use_color
    )
    write_execution_json_output(
        payload=format_scenario_execution_json(results=results, local=True),
        json_output=json_output,
        json_output_path=json_output_path,
    )
    return exit_code


def _write_local_summary(
    *, results: tuple[ScenarioRunResult, ...], stream: TextIO, use_color: bool
) -> int:
    pass_count: int = sum(
        1 for result in results if result.local_status == ScenarioLocalRunStatus.PASS
    )
    fail_count: int = sum(
        1 for result in results if result.local_status == ScenarioLocalRunStatus.FAIL
    )
    error_count: int = sum(
        1 for result in results if result.local_status == ScenarioLocalRunStatus.ERROR
    )
    skip_count: int = sum(
        1 for result in results if result.local_status == ScenarioLocalRunStatus.SKIP
    )
    stream.write(
        "\n"
        + format_summary_footer(
            counts=(
                ("PASS", pass_count),
                ("FAIL", fail_count),
                ("ERROR", error_count),
                ("SKIP", skip_count),
                ("TOTAL", len(results)),
            ),
            use_color=use_color,
        )
        + "\n"
    )
    stream.flush()
    return 0 if fail_count == 0 and error_count == 0 else 1
