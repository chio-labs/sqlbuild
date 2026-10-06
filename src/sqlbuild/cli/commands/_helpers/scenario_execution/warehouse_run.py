"""Shared warehouse-direct scenario execution."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.scenario_output.result_output import complete_scenario_run
from sqlbuild.cli.commands._helpers.scenario_output.run_presentation import (
    begin_scenario_run,
    finish_scenario_run,
)
from sqlbuild.cli.commands.constants import SUCCESS_STATUS
from sqlbuild.cli.commands.models import ScenarioRunOutputContext, ScenarioRunPresentation
from sqlbuild.cli.progress.classes.connection_progress_reporter import ConnectionProgressReporter
from sqlbuild.compiler.compile.models import CompiledSqlScenario
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.executor.pipeline.main.run import run_scenario_test_pipeline
from sqlbuild.executor.scenario.models import ScenarioRunResult
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
    concurrency: int,
    output_context: ScenarioRunOutputContext,
) -> int:
    """Run selected scenarios warehouse-direct and render results."""

    presentation: ScenarioRunPresentation = begin_scenario_run(
        context=output_context, scenario_count=len(scenarios)
    )
    execution_connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        blank_line_after_complete=True,
        stream=output_context.progress_stream,
        use_color=output_context.use_color,
    )
    results: tuple[ScenarioRunResult, ...] = run_scenario_test_pipeline(
        pipeline_result=pipeline_result,
        scenarios=scenarios,
        connection_config=connection_config,
        adapter=adapter,
        project_name=project_name,
        retain=retain,
        concurrency=concurrency,
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
            presentation.scenario_status.start(presentation.activity)
            if presentation.status_is_tty
            else None
        ),
        on_scenario_complete=lambda _scenario, scenario_plan, result: complete_scenario_run(
            scenario_status=presentation.scenario_status,
            status_is_tty=presentation.status_is_tty,
            target_dir=target_dir,
            adapter=adapter,
            scenario_plan=scenario_plan,
            result=result,
            progress_stream=output_context.progress_stream,
            use_color=output_context.use_color,
        ),
    )
    pass_count: int = sum(1 for result in results if result.status == SUCCESS_STATUS)
    fail_count: int = len(results) - pass_count
    finish_scenario_run(
        context=output_context,
        presentation=presentation,
        results=results,
        counts=(("PASS", pass_count), ("FAIL", fail_count), ("TOTAL", len(results))),
        succeeded=fail_count == 0,
        local=False,
    )
    return 0 if fail_count == 0 else 1
