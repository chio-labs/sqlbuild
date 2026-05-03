"""CLI plan command entry point."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands.main.helpers.plan.formatter import format_plan
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_project_connection_config
from sqlbuild.cli.commands.main.shared.helpers.json_output import format_plan_json
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import CursorOverrides, PlanOutput
from sqlbuild.shared.helpers.colors import supports_color


def run_plan(
    project_dir: Path | None,
    no_sql_validation: bool = False,
    defer_to: str | None = None,
    cursor_overrides: CursorOverrides | None = None,
    json_output: bool = False,
    full_refresh: bool = False,
    no_color: bool = False,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
) -> int:
    """Execute the plan command."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    pipeline_result: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=resolve_adapter(discovered_inputs.project_config.adapter),
        no_sql_validation=no_sql_validation,
        defer_to=defer_to,
        cursor_overrides=cursor_overrides,
        full_refresh=full_refresh,
        select=select,
        exclude=exclude,
        connection_config=resolve_project_connection_config(
            discovered_inputs=discovered_inputs, project_dir=effective_project_dir
        ),
    )

    plan_output: PlanOutput = pipeline_result.plan_output

    if json_output:
        print(format_plan_json(plan_output))
        return 0

    use_color: bool = not no_color and supports_color()
    print("\n" + format_plan(plan_output, full_refresh=full_refresh, use_color=use_color))
    return 0
