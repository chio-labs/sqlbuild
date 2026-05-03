"""CLI run command entry point."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_connection_config
from sqlbuild.cli.commands.main.shared.helpers.plan_format import format_plan
from sqlbuild.cli.commands.main.shared.helpers.progress import (
    BuildProgressCallbacks,
    format_build_footer,
    format_build_header,
)
from sqlbuild.cli.commands.main.shared.helpers.runtime_target_writer import write_runtime_target
from sqlbuild.compiler.discovery.main import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import CursorOverrides, PlanOutput
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.pipeline.main import run_build_pipeline
from sqlbuild.shared.helpers.colors import blue_bold, dim, supports_color


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
    adapter: BaseAdapter = resolve_adapter(discovered_inputs.project_config.adapter)
    connection_config: dict[str, object] = resolve_connection_config(
        raw_config=discovered_inputs.project_config.connection,
        project_dir=effective_project_dir,
    )
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
    )

    plan_output: PlanOutput = pipeline_result.plan_output
    use_color: bool = not no_color and supports_color()

    plan_text: str = format_plan(plan_output, full_refresh=full_refresh, use_color=use_color)
    sys.stdout.write("\n" + plan_text + "\n\n")

    callbacks: BuildProgressCallbacks = BuildProgressCallbacks(
        plan=plan_output, use_color=use_color, verbose=verbose, debug=debug
    )
    progress_stream: TextIO = sys.stderr if debug else sys.stdout
    effective_concurrency: int = (
        concurrency
        if concurrency is not None
        else discovered_inputs.project_config.settings.max_concurrency
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
        settings=discovered_inputs.project_config.settings,
        run_id=pipeline_result.project.run_id,
        run_tests=False,
        run_audits=False,
        fail_fast=fail_fast,
        max_concurrency=effective_concurrency,
        on_node_start=callbacks.on_node_start,
        on_node_complete=callbacks.on_node_complete,
        on_sub_progress=callbacks.on_sub_progress,
        custom_materializations=pipeline_result.custom_materializations,
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
