"""CLI run command entry point."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.helpers.compile.target_writer import write_compile_target
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_project_connection_config
from sqlbuild.cli.commands.main.shared.helpers.connection_progress import (
    ConnectionProgressReporter,
)
from sqlbuild.cli.commands.main.shared.helpers.plan_format import format_plan
from sqlbuild.cli.commands.main.shared.helpers.planning_progress import PlanningProgressReporter
from sqlbuild.cli.commands.main.shared.helpers.progress import (
    BuildProgressCallbacks,
    format_build_footer,
    format_build_header,
)
from sqlbuild.cli.commands.main.shared.helpers.runtime_target_writer import write_runtime_target
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import CursorOverrides, PlanOutput
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.pipeline.main.run import run_build_pipeline
from sqlbuild.shared.helpers.colors import blue_bold, dim, supports_color
from sqlbuild.spec.models.project import resolve_effective_adapter_name


def run_run(
    project_dir: Path | None,
    no_sql_validation: bool = False,
    defer_to: str | None = None,
    cursor_overrides: CursorOverrides | None = None,
    no_color: bool = False,
    fail_fast: bool = False,
    full_refresh: bool = False,
    concurrency: int | None = None,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    verbose: bool = False,
    debug: bool = False,
) -> int:
    """Execute the run command."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(
        adapter_name,
        project_dir=effective_project_dir,
    )
    connection_config: dict[str, object] = resolve_project_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=effective_project_dir,
    )
    use_color: bool = not no_color and supports_color()
    progress_stream: TextIO = sys.stderr if debug else sys.stdout
    connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        stream=progress_stream,
        use_color=use_color,
    )
    execution_connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        stream=progress_stream,
        blank_line_after_complete=True,
        use_color=use_color,
    )
    planning_progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=progress_stream,
        use_color=use_color,
    )
    progress_stream.write("\n")
    progress_stream.flush()
    pipeline_result: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        defer_to=defer_to,
        cursor_overrides=cursor_overrides,
        select=select,
        exclude=exclude,
        full_refresh=full_refresh,
        connection_config=connection_config,
        on_connection_start=connection_progress.on_connection_start,
        on_connection_complete=connection_progress.on_connection_complete,
        on_connection_error=connection_progress.on_connection_error,
        on_progress=planning_progress.on_progress,
    )

    plan_output: PlanOutput = pipeline_result.plan_output
    plan_stream: TextIO = sys.stderr if debug else sys.stdout

    plan_text: str = format_plan(plan_output, full_refresh=full_refresh, use_color=use_color)
    plan_stream.write("\n" + plan_text + "\n\n")
    plan_stream.flush()

    write_compile_target(
        target_dir=effective_project_dir / "target",
        adapter=adapter,
        plan_output=plan_output,
        manifest=pipeline_result.manifest,
    )

    callbacks: BuildProgressCallbacks = BuildProgressCallbacks(
        plan=plan_output, use_color=use_color, verbose=verbose, debug=debug
    )
    effective_concurrency: int = (
        concurrency if concurrency is not None else pipeline_result.project.settings.concurrency
    )
    header: str = format_build_header(
        command="sqb run", target=None, concurrency=effective_concurrency
    )
    execution_label: str = blue_bold("Execution") if use_color else "Execution"
    header_detail: str = dim(header) if use_color else header
    progress_stream.write(f"{execution_label}  {header_detail}\n\n")
    progress_stream.flush()

    result: BuildExecutionResult = run_build_pipeline(
        plan=plan_output,
        connection_config=connection_config,
        adapter=adapter,
        settings=pipeline_result.project.settings,
        run_id=pipeline_result.project.run_id,
        run_tests=False,
        run_audits=False,
        fail_fast=fail_fast,
        max_concurrency=effective_concurrency,
        on_node_start=callbacks.on_node_start,
        on_node_complete=callbacks.on_node_complete,
        on_sub_progress=callbacks.on_sub_progress,
        custom_materializations=pipeline_result.custom_materializations,
        on_connection_start=execution_connection_progress.on_connection_start,
        on_connection_complete=execution_connection_progress.on_connection_complete,
        on_connection_error=execution_connection_progress.on_connection_error,
    )
    write_runtime_target(
        target_dir=effective_project_dir / "target",
        plan_output=plan_output,
        result=result,
    )

    footer: str = format_build_footer(result=result, elapsed=callbacks.elapsed, use_color=use_color)
    progress_stream.write("\n" + footer + "\n")
    progress_stream.flush()

    return 0 if result.status == BuildStatus.SUCCESS else 1
