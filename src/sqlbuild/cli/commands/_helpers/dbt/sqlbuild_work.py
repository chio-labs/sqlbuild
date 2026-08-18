"""SQLBuild work helpers for dbt interop commands."""

from __future__ import annotations

from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands.classes.build_progress_callbacks import (
    BuildProgressCallbacks,
    format_build_footer,
)
from sqlbuild.cli.commands.models import DbtSqlbuildWorkContext
from sqlbuild.cli.progress.classes.connection_progress_reporter import ConnectionProgressReporter
from sqlbuild.cli.progress.main._execution_header import format_execution_header
from sqlbuild.cli.target_artifacts.main._write_runtime_target import write_runtime_target
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.planner.models import (
    PlanOutput,
)
from sqlbuild.executor.build.models import (
    BuildCallbacks,
    BuildExecutionResult,
    BuildRuntimeParams,
)
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.pipeline.main.run import (
    run_build_pipeline,
)
from sqlbuild.integrations.dbt.types import DbtInteropCommand
from sqlbuild.presentation.classes.cli_style import CliStyle


def execute_sqlbuild_build_work(
    *,
    context: DbtSqlbuildWorkContext,
    command: DbtInteropCommand,
    project: CompiledProject,
    project_dir: Path,
    fail_fast: bool,
    verbose: bool,
) -> int:
    plan_output: PlanOutput = context.plan_output
    connection_config: dict[str, object] = context.connection_config
    adapter: BaseAdapter = context.adapter
    adapter_name: str = context.adapter_name
    output_stream: TextIO = context.output_stream
    use_color: bool = context.use_color
    callbacks: BuildProgressCallbacks = BuildProgressCallbacks(
        plan=plan_output, use_color=use_color, verbose=verbose, debug=False
    )
    effective_concurrency: int = project.settings.concurrency
    display_command: str = (
        "sqb build --no-tests --no-audits"
        if command == DbtInteropCommand.RUN
        else f"sqb {command.value}"
    )
    header: str = format_execution_header(
        command=display_command, target=None, concurrency=effective_concurrency
    )
    style: CliStyle = CliStyle(use_color=use_color)
    execution_label: str = style.object_name("SQLBuild execution")
    header_detail: str = style.muted(header)
    output_stream.write(f"{execution_label}  {header_detail}\n\n")
    output_stream.flush()
    execution_connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        stream=output_stream,
        blank_line_after_complete=True,
        use_color=use_color,
    )
    result: BuildExecutionResult = run_build_pipeline(
        plan=plan_output,
        connection_config=connection_config,
        adapter=adapter,
        settings=project.settings,
        runtime=BuildRuntimeParams(
            run_id=project.run_id,
            run_tests=command == DbtInteropCommand.BUILD,
            run_audits=command == DbtInteropCommand.BUILD,
            fail_fast=fail_fast,
            max_concurrency=effective_concurrency,
            use_color=use_color,
        ),
        callbacks=BuildCallbacks(
            on_node_start=lambda name, resource_kind: callbacks.on_node_start(
                name=name, resource_kind=resource_kind
            ),
            on_node_complete=callbacks.on_node_complete,
            on_sub_progress=callbacks.on_sub_progress,
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
    )
    write_runtime_target(target_dir=project_dir / "target", plan_output=plan_output, result=result)
    footer: str = format_build_footer(result=result, elapsed=callbacks.elapsed, use_color=use_color)
    output_stream.write("\n" + footer + "\n")
    output_stream.flush()
    return 0 if result.status == BuildStatus.SUCCESS else 1
