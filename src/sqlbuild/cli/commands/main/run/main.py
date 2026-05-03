"""CLI run command entry point."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.colors import supports_color
from sqlbuild.cli.commands.main.shared.helpers.plan_format import format_plan
from sqlbuild.cli.commands.main.shared.helpers.progress import (
    BuildProgressCallbacks,
    format_build_footer,
    format_build_header,
)
from sqlbuild.compiler.discovery.main import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import CursorOverrides, PlanOutput
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.pipeline.main import run_build_pipeline


def run_run(
    project_dir: Path | None,
    no_sql_validation: bool = False,
    defer_to: str | None = None,
    cursor_overrides: CursorOverrides | None = None,
    no_color: bool = False,
    fail_fast: bool = False,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
) -> int:
    """Execute the run command."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    adapter: BaseAdapter = resolve_adapter(discovered_inputs.project_config.adapter)
    pipeline_result: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        defer_to=defer_to,
        cursor_overrides=cursor_overrides,
        select=select,
        exclude=exclude,
    )

    plan_output: PlanOutput = pipeline_result.plan_output
    use_color: bool = not no_color and supports_color()

    plan_text: str = format_plan(plan_output, use_color=use_color)
    sys.stdout.write(plan_text + "\n\n")

    callbacks: BuildProgressCallbacks = BuildProgressCallbacks(
        plan=plan_output, use_color=use_color
    )
    header: str = format_build_header(command="sqb run", target=None, concurrency=1)
    sys.stdout.write(header + "\n\n")
    sys.stdout.flush()

    result: BuildExecutionResult = run_build_pipeline(
        plan=plan_output,
        connection_config=dict(discovered_inputs.project_config.connection),
        adapter=adapter,
        settings=discovered_inputs.project_config.settings,
        run_id=pipeline_result.project.run_id,
        run_tests=False,
        run_audits=False,
        fail_fast=fail_fast,
        on_node_start=callbacks.on_node_start,
        on_node_complete=callbacks.on_node_complete,
    )

    footer: str = format_build_footer(result=result, elapsed=callbacks.elapsed, use_color=use_color)
    sys.stdout.write("\n" + footer + "\n")
    sys.stdout.flush()

    return 0 if result.status == BuildStatus.SUCCESS else 1
