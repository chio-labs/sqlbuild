"""dbt scenario test/capture orchestration."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.types import BuiltinAdapter
from sqlbuild.cli.commands.main.helpers.scenario.capture_run import run_scenario_capture_run
from sqlbuild.cli.commands.main.helpers.scenario.dialect import require_scenario_capture_dialect
from sqlbuild.cli.commands.main.helpers.scenario.local_run import run_local_scenarios
from sqlbuild.cli.commands.main.helpers.scenario.selection import select_scenarios
from sqlbuild.cli.commands.main.helpers.scenario.snapshot_limits import (
    build_scenario_snapshot_capture_limits,
    scenario_snapshot_capture_warning,
)
from sqlbuild.cli.commands.main.helpers.scenario.warehouse_run import run_warehouse_scenarios
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.cli.commands.main.shared.helpers.config.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.config.parsers import (
    add_execution_json_output_arg,
    add_select_args,
)
from sqlbuild.cli.commands.main.shared.helpers.progress.planning import PlanningProgressReporter
from sqlbuild.compiler.compile.models.core import CompiledSqlScenario
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.integrations.dbt.models import DbtScenarioBuild
from sqlbuild.integrations.dbt.pipeline.main.scenario import build_dbt_scenario_project
from sqlbuild.shared.constants import (
    SCENARIO_CLI_LOCAL_RETAIN_UNSUPPORTED,
    SCENARIO_CLI_LOCAL_SNAPSHOT_FLAG_REQUIRED,
)
from sqlbuild.shared.helpers.colors import supports_color


def run_dbt_scenario_test(
    *, project_dir: Path | None, args: tuple[str, ...], no_color: bool
) -> int:
    """Run `sqb dbt scenario test` warehouse-direct or on local DuckDB."""

    parser: argparse.ArgumentParser = argparse.ArgumentParser(prog="sqb dbt scenario test")
    parser.add_argument("scenario_selector", nargs="*", metavar="scenario")
    parser.add_argument("--retain", action="store_true", default=False)
    parser.add_argument("--local", action="store_true", default=False)
    parser.add_argument("--strict", action="store_true", default=False)
    parser.add_argument(
        "--sync-snapshots", dest="sync_snapshots", action="store_true", default=False
    )
    parser.add_argument("--refresh", action="store_true", default=False)
    parser.add_argument("--json", action="store_true", default=False)
    add_execution_json_output_arg(parser)
    add_select_args(parser)
    parsed: argparse.Namespace = parser.parse_args(list(args))
    json_output: bool = bool(parsed.json)
    retain: bool = bool(parsed.retain)
    local: bool = bool(parsed.local)
    strict: bool = bool(parsed.strict)
    sync_snapshots: bool = bool(parsed.sync_snapshots)
    refresh: bool = bool(parsed.refresh)
    json_output_path: Path | None = parsed.json_output
    selectors: tuple[str, ...] = (*parsed.scenario_selector, *parsed.select)
    exclude: tuple[str, ...] = tuple(parsed.exclude)
    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    use_color: bool = not no_color and not json_output and supports_color()
    progress_stream: TextIO = sys.stderr if json_output else sys.stdout

    if local and retain:
        raise CliUserError(
            "dbt scenario test --local does not support --retain",
            code=SCENARIO_CLI_LOCAL_RETAIN_UNSUPPORTED,
            help="Local scenario DuckDB files are always kept under target/run/scenarios/.",
        )
    if not local and (sync_snapshots or refresh):
        raise CliUserError(
            "dbt scenario snapshot sync flags require --local",
            code=SCENARIO_CLI_LOCAL_SNAPSHOT_FLAG_REQUIRED,
            help=(
                "Use sqb dbt scenario test --local --sync-snapshots or "
                "sqb dbt scenario test --local --refresh."
            ),
        )
    if local and (sync_snapshots or refresh):
        sync_exit_code: int = capture_dbt_scenarios(
            project_dir=effective_project_dir,
            selectors=selectors,
            exclude=exclude,
            force=refresh,
            progress_stream=progress_stream,
            use_color=use_color,
        )
        if sync_exit_code != 0:
            return sync_exit_code

    discovery: DbtScenarioBuild = _build_dbt_scenario(
        project_dir=effective_project_dir,
        selectors=selectors,
        progress_stream=progress_stream,
        use_color=use_color,
    )
    scenarios: tuple[CompiledSqlScenario, ...] = select_scenarios(
        project=discovery.project,
        selectors=selectors,
        exclude=exclude,
        project_dir=effective_project_dir,
    )
    if not scenarios:
        progress_stream.write("\nNo scenarios selected.\n")
        progress_stream.flush()
        return 0
    pipeline_result: CompilePipelineResult = CompilePipelineResult(
        project=discovery.project,
        plan_output=PlanOutput(),
    )
    if local:
        project_adapter: BaseAdapter = resolve_adapter(
            discovery.adapter_name, project_dir=effective_project_dir
        )
        return run_local_scenarios(
            project_dir=effective_project_dir,
            pipeline_result=pipeline_result,
            scenarios=scenarios,
            adapter=resolve_adapter(BuiltinAdapter.DUCKDB.value, project_dir=effective_project_dir),
            project_name=discovery.project_name,
            strict=strict,
            capture_adapter=discovery.adapter_name,
            capture_dialect=require_scenario_capture_dialect(
                adapter=project_adapter, adapter_name=discovery.adapter_name
            ),
            target_dir=effective_project_dir / "target",
            progress_stream=progress_stream,
            use_color=use_color,
            json_output=json_output,
            json_output_path=json_output_path,
        )
    return run_warehouse_scenarios(
        pipeline_result=pipeline_result,
        scenarios=scenarios,
        connection_config=discovery.connection_config,
        adapter=resolve_adapter(discovery.adapter_name, project_dir=effective_project_dir),
        adapter_name=discovery.adapter_name,
        project_name=discovery.project_name,
        target_dir=effective_project_dir / "target",
        retain=retain,
        progress_stream=progress_stream,
        use_color=use_color,
        json_output=json_output,
        json_output_path=json_output_path,
    )


def run_dbt_scenario_capture(
    *, project_dir: Path | None, args: tuple[str, ...], no_color: bool
) -> int:
    """Run `sqb dbt scenario capture` to write warehouse snapshots."""

    parser: argparse.ArgumentParser = argparse.ArgumentParser(prog="sqb dbt scenario capture")
    parser.add_argument("scenario_selector", nargs="*", metavar="scenario")
    parser.add_argument("--retain", action="store_true", default=False)
    parser.add_argument("--force", action="store_true", default=False)
    add_select_args(parser)
    parsed: argparse.Namespace = parser.parse_args(list(args))
    selectors: tuple[str, ...] = (*parsed.scenario_selector, *parsed.select)
    exclude: tuple[str, ...] = tuple(parsed.exclude)
    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    use_color: bool = not no_color and supports_color()
    progress_stream: TextIO = sys.stdout
    progress_stream.write("\n")
    progress_stream.write(f"{scenario_snapshot_capture_warning(force=bool(parsed.force))}\n")
    progress_stream.flush()
    return capture_dbt_scenarios(
        project_dir=effective_project_dir,
        selectors=selectors,
        exclude=exclude,
        force=bool(parsed.force),
        retain=bool(parsed.retain),
        progress_stream=progress_stream,
        use_color=use_color,
    )


def capture_dbt_scenarios(
    *,
    project_dir: Path,
    selectors: tuple[str, ...],
    exclude: tuple[str, ...],
    force: bool,
    progress_stream: TextIO,
    use_color: bool,
    retain: bool = False,
) -> int:
    """Compile dbt and capture selected scenarios to durable snapshots."""

    discovery: DbtScenarioBuild = _build_dbt_scenario(
        project_dir=project_dir,
        selectors=selectors,
        progress_stream=progress_stream,
        use_color=use_color,
    )
    scenarios: tuple[CompiledSqlScenario, ...] = select_scenarios(
        project=discovery.project,
        selectors=selectors,
        exclude=exclude,
        project_dir=project_dir,
    )
    if not scenarios:
        progress_stream.write("\nNo scenarios selected.\n")
        progress_stream.flush()
        return 0
    adapter: BaseAdapter = resolve_adapter(discovery.adapter_name, project_dir=project_dir)
    pipeline_result: CompilePipelineResult = CompilePipelineResult(
        project=discovery.project,
        plan_output=PlanOutput(),
    )
    return run_scenario_capture_run(
        project_dir=project_dir,
        pipeline_result=pipeline_result,
        scenarios=scenarios,
        connection_config=discovery.connection_config,
        adapter=adapter,
        adapter_name=discovery.adapter_name,
        project_name=discovery.project_name,
        capture_dialect=require_scenario_capture_dialect(
            adapter=adapter, adapter_name=discovery.adapter_name
        ),
        capture_limits=build_scenario_snapshot_capture_limits(
            scenario_config=discovery.scenario_config,
            max_rows_per_relation=None,
            max_total_rows=None,
            max_bytes_per_relation=None,
            max_total_bytes=None,
            force=force,
        ),
        retain=retain,
        progress_stream=progress_stream,
        use_color=use_color,
    )


def _build_dbt_scenario(
    *,
    project_dir: Path,
    selectors: tuple[str, ...],
    progress_stream: TextIO,
    use_color: bool,
) -> DbtScenarioBuild:
    planning_progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=progress_stream,
        use_color=use_color,
    )
    progress_stream.write("\n")
    progress_stream.flush()
    return build_dbt_scenario_project(
        project_dir=project_dir,
        expected_model_names=(),
        select=selectors,
        on_progress=planning_progress.on_progress,
    )
