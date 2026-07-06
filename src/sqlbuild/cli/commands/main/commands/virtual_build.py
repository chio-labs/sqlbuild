"""CLI orchestration for virtual-mode build."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.helpers.build.models import (
    VirtualBuildCliRequest,
    VirtualBuildPlanHookConfig,
)
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
from sqlbuild.virtual.executor.main.build import run_virtual_build as run_virtual_build_pipeline
from sqlbuild.virtual.executor.models import (
    VirtualBuildHooks,
    VirtualBuildOptions,
    VirtualBuildPipelineResult,
)


def run_virtual_build(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    adapter_name: str,
    connection_config: dict[str, object],
    request: VirtualBuildCliRequest,
    progress_stream: TextIO | None = None,
) -> int:
    """Execute a virtual build and render CLI output."""

    stream: TextIO = progress_stream or (
        sys.stderr if request.debug or request.json_output else sys.stdout
    )
    stream.write("\n")
    stream.flush()
    connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        stream=stream,
        use_color=request.use_color,
    )
    planning_progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=stream,
        use_color=request.use_color,
    )
    plan_hook: VirtualBuildPlanHook = VirtualBuildPlanHook(
        stream=stream,
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        config=VirtualBuildPlanHookConfig(
            full_refresh=request.full_refresh,
            allow_snapshot_full_refresh=request.allow_snapshot_full_refresh,
            use_color=request.use_color,
            verbose=request.verbose,
            debug=request.debug,
            json_output=request.json_output,
            execution_command=request.execution_command,
            concurrency=request.concurrency,
        ),
    )
    cursor_overrides: CursorOverrides = request.cursor_overrides or CursorOverrides()
    result: VirtualBuildPipelineResult = run_virtual_build_pipeline(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        connection_config=connection_config,
        options=VirtualBuildOptions(
            selected_target=request.selected_target,
            no_sql_validation=request.no_sql_validation,
            defer_sources_to=request.defer_sources_to,
            cursor_overrides=request.cursor_overrides,
            full_refresh=request.full_refresh,
            virtual_environment_name=request.virtual_environment_name,
            include_stale_upstreams=request.include_stale_upstreams,
            changes_only=request.changes_only,
            auto_load_sources=request.auto_load_sources,
            reload_sources=request.reload_sources,
            include_python=request.include_python,
            seed_only=request.seed_only,
            select=request.select,
            exclude=request.exclude,
            fail_fast=request.fail_fast,
            allow_snapshot_schema_change=request.allow_snapshot_schema_change,
            concurrency=request.concurrency,
            cli_vars=request.cli_vars,
            run_tests=request.run_tests,
            run_audits=request.run_audits,
            snapshots=discovered_inputs.project_config.snapshots,
            start_cursor_ts=parse_cursor_timestamp(cursor_overrides.start_ts),
            end_cursor_ts=parse_cursor_timestamp(cursor_overrides.end_ts),
            start_cursor_int=parse_cursor_integer(cursor_overrides.start_int),
            end_cursor_int=parse_cursor_integer(cursor_overrides.end_int),
            external_sql_reference_resolver=request.external_sql_reference_resolver,
            providers=request.providers,
        ),
        hooks=VirtualBuildHooks(
            on_plan_ready=plan_hook.on_plan_ready,
            on_progress=planning_progress.on_progress,
            on_connection_start=connection_progress.on_connection_start,
            on_connection_complete=connection_progress.on_connection_complete,
            on_connection_error=connection_progress.on_connection_error,
        ),
    )
    plan_output: PlanOutput = result.display_plan_output
    write_python_node_results(
        stream=stream,
        results=result.python_node_results,
        use_color=request.use_color,
    )
    check_results: tuple[PythonCheckExecutionResult, ...] = run_post_virtual_build_checks(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        connection_config=connection_config,
        result=result,
        exclude=request.exclude,
        reload_sources=request.reload_sources,
        providers=request.providers,
        stream=stream,
        use_color=request.use_color,
    )
    footer: str = format_build_footer(
        result=result.execution_result,
        elapsed=plan_hook.elapsed,
        use_color=request.use_color,
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
            command=request.execution_command,
        ),
        json_output=request.json_output,
        json_output_path=request.json_output_path,
    )
    return (
        0
        if result.execution_result.status == BuildStatus.SUCCESS
        and not check_results_failed(check_results)
        else 1
    )
