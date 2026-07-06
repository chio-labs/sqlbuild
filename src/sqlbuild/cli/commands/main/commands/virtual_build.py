"""CLI orchestration for virtual-mode build."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.helpers.build.plan_hook import VirtualBuildPlanHook
from sqlbuild.cli.commands.helpers.build.virtual_checks import run_post_virtual_build_checks
from sqlbuild.cli.commands.helpers.check.core import check_results_failed
from sqlbuild.cli.commands.shared.helpers.config.parsers import (
    parse_cursor_integer,
    parse_cursor_timestamp,
)
from sqlbuild.cli.commands.shared.helpers.output.execution_json import (
    format_build_execution_json,
    write_execution_json_output,
)
from sqlbuild.cli.commands.shared.helpers.progress.connection import (
    ConnectionProgressReporter,
)
from sqlbuild.cli.commands.shared.helpers.progress.core import format_build_footer
from sqlbuild.cli.commands.shared.helpers.progress.planning import (
    PlanningProgressReporter,
)
from sqlbuild.cli.commands.shared.helpers.python_nodes.core import write_python_node_results
from sqlbuild.cli.commands.shared.helpers.targets.runtime import (
    write_python_check_runtime_target,
    write_runtime_target,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.planner.models import CursorOverrides, PlanOutput
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.python_nodes.models import PythonCheckExecutionResult
from sqlbuild.provider.main.runtime import ProviderContainer
from sqlbuild.shared.types import ExternalSqlReferenceResolver
from sqlbuild.virtual.executor.main.build import run_virtual_build as run_virtual_build_pipeline
from sqlbuild.virtual.executor.models import VirtualBuildPipelineResult


def run_virtual_build(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    adapter_name: str,
    connection_config: dict[str, object],
    selected_target: str | None = None,
    no_sql_validation: bool = False,
    defer_sources_to: str | None = None,
    cursor_overrides: CursorOverrides | None = None,
    full_refresh: bool = False,
    virtual_environment_name: str | None = None,
    include_stale_upstreams: bool = False,
    changes_only: bool = False,
    auto_load_sources: bool = False,
    reload_sources: bool = False,
    include_python: bool = True,
    seed_only: bool = False,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    fail_fast: bool = False,
    allow_snapshot_full_refresh: bool = False,
    allow_snapshot_schema_change: bool = False,
    concurrency: int | None = None,
    verbose: bool = False,
    debug: bool = False,
    cli_vars: dict[str, object] | None = None,
    run_tests: bool = True,
    run_audits: bool = True,
    json_output: bool = False,
    json_output_path: Path | None = None,
    execution_command: str = "build",
    use_color: bool = False,
    progress_stream: TextIO | None = None,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
    providers: ProviderContainer | None = None,
) -> int:
    """Execute a virtual build and render CLI output."""

    stream: TextIO = progress_stream or (sys.stderr if debug or json_output else sys.stdout)
    stream.write("\n")
    stream.flush()
    connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        stream=stream,
        use_color=use_color,
    )
    planning_progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=stream,
        use_color=use_color,
    )
    plan_hook: VirtualBuildPlanHook = VirtualBuildPlanHook(
        stream=stream,
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        full_refresh=full_refresh,
        allow_snapshot_full_refresh=allow_snapshot_full_refresh,
        use_color=use_color,
        verbose=verbose,
        debug=debug,
        json_output=json_output,
        execution_command=execution_command,
        concurrency=concurrency,
    )
    result: VirtualBuildPipelineResult = run_virtual_build_pipeline(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        connection_config=connection_config,
        selected_target=selected_target,
        no_sql_validation=no_sql_validation,
        defer_sources_to=defer_sources_to,
        cursor_overrides=cursor_overrides,
        full_refresh=full_refresh,
        virtual_environment_name=virtual_environment_name,
        include_stale_upstreams=include_stale_upstreams,
        changes_only=changes_only,
        auto_load_sources=auto_load_sources,
        reload_sources=reload_sources,
        include_python=include_python,
        seed_only=seed_only,
        select=select,
        exclude=exclude,
        fail_fast=fail_fast,
        allow_snapshot_schema_change=allow_snapshot_schema_change,
        concurrency=concurrency,
        cli_vars=cli_vars,
        run_tests=run_tests,
        run_audits=run_audits,
        snapshots=discovered_inputs.project_config.snapshots,
        start_cursor_ts=parse_cursor_timestamp((cursor_overrides or CursorOverrides()).start_ts),
        end_cursor_ts=parse_cursor_timestamp((cursor_overrides or CursorOverrides()).end_ts),
        start_cursor_int=parse_cursor_integer((cursor_overrides or CursorOverrides()).start_int),
        end_cursor_int=parse_cursor_integer((cursor_overrides or CursorOverrides()).end_int),
        on_plan_ready=plan_hook.on_plan_ready,
        on_connection_start=connection_progress.on_connection_start,
        on_connection_complete=connection_progress.on_connection_complete,
        on_connection_error=connection_progress.on_connection_error,
        on_progress=planning_progress.on_progress,
        external_sql_reference_resolver=external_sql_reference_resolver,
        providers=providers,
    )
    plan_output: PlanOutput = result.display_plan_output
    write_python_node_results(
        stream=stream,
        results=result.python_node_results,
        use_color=use_color,
    )
    check_results: tuple[PythonCheckExecutionResult, ...] = run_post_virtual_build_checks(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        connection_config=connection_config,
        result=result,
        exclude=exclude,
        reload_sources=reload_sources,
        providers=providers,
        stream=stream,
        use_color=use_color,
    )
    footer: str = format_build_footer(
        result=result.execution_result,
        elapsed=plan_hook.elapsed,
        use_color=use_color,
        python_node_results=result.python_node_results,
    )
    write_runtime_target(
        target_dir=project_dir / "target",
        plan_output=plan_output,
        result=result.execution_result,
    )
    write_python_check_runtime_target(target_dir=project_dir / "target", results=check_results)
    stream.write("\n" + footer + "\n")
    stream.flush()
    write_execution_json_output(
        payload=format_build_execution_json(
            result=result.execution_result,
            plan=plan_output,
            python_node_results=result.python_node_results,
            python_check_results=check_results,
            command=execution_command,
        ),
        json_output=json_output,
        json_output_path=json_output_path,
    )
    return (
        0
        if result.execution_result.status == BuildStatus.SUCCESS
        and not check_results_failed(check_results)
        else 1
    )
