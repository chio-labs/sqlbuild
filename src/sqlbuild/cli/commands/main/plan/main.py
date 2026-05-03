"""CLI plan command entry point."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands.main.plan.helpers.formatter import (
    format_plan_compact,
    format_plan_verbose,
)
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.compiler.discovery.main import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import PlanOutput


def run_plan(
    project_dir: Path | None,
    no_sql_validation: bool = False,
    defer_to: str | None = None,
    verbose: bool = False,
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
    )

    plan_output: PlanOutput = pipeline_result.plan_output
    output: str = _format_output(plan_output=plan_output, verbose=verbose)
    print(output)
    return 0


def _format_output(*, plan_output: PlanOutput, verbose: bool) -> str:
    """Select and run the appropriate formatter."""

    if verbose:
        return format_plan_verbose(plan_output)
    return format_plan_compact(plan_output)
