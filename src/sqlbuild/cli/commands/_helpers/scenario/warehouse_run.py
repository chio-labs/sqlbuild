"""Shared warehouse-direct scenario execution."""

from __future__ import annotations

from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.scenario.constants import SUCCESS_STATUS
from sqlbuild.cli.commands._helpers.scenario.models import ScenarioRunOutputContext
from sqlbuild.cli.commands._helpers.scenario.result_output import complete_scenario_run
from sqlbuild.cli.output.main.scenario_execution_json import (
    format_scenario_execution_json,
)
from sqlbuild.cli.output.main.write_execution_json_output import write_execution_json_output
from sqlbuild.cli.progress.classes.connection_progress_reporter import ConnectionProgressReporter
from sqlbuild.compiler.compile.models import CompiledSqlScenario
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.executor.pipeline.main.run import run_scenario_test_pipeline
from sqlbuild.executor.scenario.models import ScenarioRunResult
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.classes.transient_status_reporter import TransientStatusReporter
from sqlbuild.presentation.main.summary_footer import format_summary_footer
from sqlbuild.runtime.contracts.models import ConnectionHooks


def run_warehouse_scenarios(
    *,
    pipeline_result: CompilePipelineResult,
    scenarios: tuple[CompiledSqlScenario, ...],
    connection_config: dict[str, object],
    adapter: BaseAdapter,
    adapter_name: str,
    project_name: str,
    target_dir: Path,
    retain: bool,
    output_context: ScenarioRunOutputContext,
) -> int:
    """Run selected scenarios warehouse-direct and render results."""

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
    execution_connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        blank_line_after_complete=True,
        stream=progress_stream,
        use_color=use_color,
    )
    results: tuple[ScenarioRunResult, ...] = run_scenario_test_pipeline(
        pipeline_result=pipeline_result,
        scenarios=scenarios,
        connection_config=connection_config,
        adapter=adapter,
        project_name=project_name,
        retain=retain,
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
    exit_code: int = _write_remote_summary(
        results=results, stream=progress_stream, use_color=use_color
    )
    write_execution_json_output(
        payload=format_scenario_execution_json(results=results, local=False),
        json_output=json_output,
        json_output_path=json_output_path,
    )
    return exit_code


def _write_remote_summary(
    *, results: tuple[ScenarioRunResult, ...], stream: TextIO, use_color: bool
) -> int:
    pass_count: int = sum(1 for result in results if result.status == SUCCESS_STATUS)
    fail_count: int = len(results) - pass_count
    stream.write(
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
    stream.flush()
    return 0 if fail_count == 0 else 1
