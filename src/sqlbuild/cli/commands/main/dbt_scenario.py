"""CLI dbt scenario command entry point."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.helpers.scenario.selection import select_scenarios
from sqlbuild.cli.commands.main.helpers.scenario.warehouse_run import run_warehouse_scenarios
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.planning_progress import PlanningProgressReporter
from sqlbuild.compiler.compile.models.core import CompiledSqlScenario
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.integrations.dbt.models import DbtScenarioBuild
from sqlbuild.integrations.dbt.pipeline.main.scenario import build_dbt_scenario_project
from sqlbuild.shared.helpers.colors import supports_color


def run_dbt_scenario_command(
    *, project_dir: Path | None, args: tuple[str, ...], no_color: bool
) -> int:
    """Execute `sqb dbt scenario test`."""

    json_output: bool = "--json" in args
    retain: bool = "--retain" in args
    selectors: tuple[str, ...] = tuple(
        arg
        for index, arg in enumerate(args)
        if arg not in {"--json", "--retain"} and not (index == 0 and arg == "test")
    )
    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    use_color: bool = not no_color and not json_output and supports_color()
    progress_stream: TextIO = sys.stderr if json_output else sys.stdout
    planning_progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=progress_stream,
        use_color=use_color,
    )
    progress_stream.write("\n")
    progress_stream.flush()

    discovery: DbtScenarioBuild = build_dbt_scenario_project(
        project_dir=effective_project_dir,
        expected_model_names=(),
        select=selectors,
        on_progress=planning_progress.on_progress,
    )
    scenarios: tuple[CompiledSqlScenario, ...] = select_scenarios(
        project=discovery.project,
        selectors=selectors,
        project_dir=effective_project_dir,
    )
    if not scenarios:
        progress_stream.write("\nNo scenarios selected.\n")
        progress_stream.flush()
        return 0
    adapter: BaseAdapter = resolve_adapter(
        discovery.adapter_name, project_dir=effective_project_dir
    )
    pipeline_result: CompilePipelineResult = CompilePipelineResult(
        project=discovery.project,
        plan_output=PlanOutput(),
    )
    return run_warehouse_scenarios(
        pipeline_result=pipeline_result,
        scenarios=scenarios,
        connection_config=discovery.connection_config,
        adapter=adapter,
        adapter_name=discovery.adapter_name,
        project_name=discovery.project_name,
        target_dir=effective_project_dir / "target",
        retain=retain,
        progress_stream=progress_stream,
        use_color=use_color,
        json_output=json_output,
    )
