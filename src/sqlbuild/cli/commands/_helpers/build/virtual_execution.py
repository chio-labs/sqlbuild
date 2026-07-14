"""Virtual build CLI execution phase."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.build.models import (
    VirtualBuildCliRequest,
    VirtualBuildExecution,
    VirtualBuildPlanHookConfig,
)
from sqlbuild.cli.commands._helpers.input.parsing import (
    parse_cursor_integer,
    parse_cursor_timestamp,
)
from sqlbuild.cli.commands.classes.virtual_build_plan_hook import VirtualBuildPlanHook
from sqlbuild.cli.progress.classes.connection_progress_reporter import (
    ConnectionProgressReporter,
)
from sqlbuild.cli.progress.classes.planning_progress_reporter import (
    PlanningProgressReporter,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.planner.models import CursorOverrides
from sqlbuild.virtual.executor.main.build import run_virtual_build as run_virtual_build_pipeline
from sqlbuild.virtual.executor.models import (
    VirtualBuildHooks,
    VirtualBuildOptions,
    VirtualBuildPipelineResult,
)


def execute_virtual_build(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    adapter_name: str,
    connection_config: dict[str, object],
    request: VirtualBuildCliRequest,
    progress_stream: TextIO | None,
) -> VirtualBuildExecution:
    """Prepare virtual build reporting and execute the pipeline."""

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
            on_plan_ready=lambda project, plan_output, python_plan_entries: plan_hook.on_plan_ready(
                project=project,
                plan_output=plan_output,
                python_plan_entries=python_plan_entries,
            ),
            on_progress=planning_progress.on_progress,
            on_connection_start=connection_progress.on_connection_start,
            on_connection_complete=lambda connection_count, elapsed_seconds: (
                connection_progress.on_connection_complete(
                    connection_count=connection_count,
                    elapsed_seconds=elapsed_seconds,
                )
            ),
            on_connection_error=lambda connection_count, elapsed_seconds: (
                connection_progress.on_connection_error(
                    connection_count=connection_count,
                    elapsed_seconds=elapsed_seconds,
                )
            ),
        ),
    )
    return VirtualBuildExecution(result=result, stream=stream, elapsed=plan_hook.elapsed)
