"""CLI compile command entry point."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.helpers.compile.models import WrittenTarget
from sqlbuild.cli.commands.main.helpers.compile.target_writer import write_compile_target
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_project_connection_config
from sqlbuild.cli.commands.main.shared.helpers.json_output import format_compile_json
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.spec.models.project import resolve_effective_adapter_name


def run_compile(
    project_dir: Path | None,
    no_sql_validation: bool = False,
    defer_to: str | None = None,
    json_output: bool = False,
) -> int:
    """Execute the compile command."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    adapter: BaseAdapter = resolve_adapter(
        resolve_effective_adapter_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        ),
        project_dir=effective_project_dir,
    )
    pipeline_result: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        defer_to=defer_to,
        connection_config=resolve_project_connection_config(
            discovered_inputs=discovered_inputs, project_dir=effective_project_dir
        ),
    )

    plan_output: PlanOutput = pipeline_result.plan_output
    written: WrittenTarget = write_compile_target(
        target_dir=effective_project_dir / "target",
        adapter=adapter,
        plan_output=plan_output,
        manifest=pipeline_result.manifest,
    )

    if json_output:
        print(format_compile_json(plan_output))
        return 0

    _print_summary(written=written, plan_output=plan_output)
    return 0


def _print_summary(*, written: WrittenTarget, plan_output: PlanOutput) -> None:
    """Print compile output summary."""

    print(written.summary_line())
    print()
    print(f"{'target/compiled/':20s} resolved SQL")
    print("target/manifest.json")

    if len(plan_output.model_entries) == 1:
        print()
        print(f"-- {plan_output.model_entries[0].name} --")
        print(plan_output.model_entries[0].resolved_sql)
