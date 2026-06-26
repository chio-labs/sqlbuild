"""CLI plan command entry point."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.helpers.plan.formatter import format_plan
from sqlbuild.cli.commands.main.shared.helpers.config.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.config.mode import (
    enforce_no_defer_to_in_virtual_mode,
)
from sqlbuild.cli.commands.main.shared.helpers.connection.core import (
    resolve_project_connection_config,
)
from sqlbuild.cli.commands.main.shared.helpers.connection.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.cli.commands.main.shared.helpers.output.json import format_plan_json
from sqlbuild.cli.commands.main.shared.helpers.progress.connection import (
    ConnectionProgressReporter,
)
from sqlbuild.cli.commands.main.shared.helpers.progress.planning import PlanningProgressReporter
from sqlbuild.compiler.compile.main.effective_settings import build_effective_settings_config
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import CursorOverrides, PlanOutput
from sqlbuild.shared.helpers.colors import supports_color
from sqlbuild.shared.helpers.display import DisplayOptions
from sqlbuild.spec.models.project import resolve_effective_adapter_name
from sqlbuild.spec.models.targets import resolve_effective_force
from sqlbuild.virtual.planner.main.plan import run_virtual_plan_pipeline


def run_plan(
    project_dir: Path | None,
    no_sql_validation: bool = False,
    defer_to: str | None = None,
    defer_sources_to: str | None = None,
    selected_target: str | None = None,
    cursor_overrides: CursorOverrides | None = None,
    json_output: bool = False,
    full_refresh: bool = False,
    virtual_env: str | None = None,
    load_sources: bool | None = None,
    include_python: bool = True,
    no_color: bool = False,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    verbose: bool = False,
    cli_vars: dict[str, object] | None = None,
    include_stale_upstreams: bool = False,
    force: bool = False,
) -> int:
    """Execute the plan command."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    effective_force: bool = resolve_effective_force(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_target=selected_target,
        cli_force=force,
    )
    enforce_no_defer_to_in_virtual_mode(
        discovered_inputs=discovered_inputs,
        command_name="plan",
        defer_to=defer_to,
    )
    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(
        adapter_name,
        project_dir=effective_project_dir,
    )
    connection_config: dict[str, object] = resolve_project_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=effective_project_dir,
        selected_target=selected_target,
        cli_vars=cli_vars,
    )
    use_color: bool = not no_color and not json_output and supports_color()
    progress_stream: TextIO = sys.stderr if json_output else sys.stdout
    connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        stream=progress_stream,
        use_color=use_color,
    )
    planning_progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=progress_stream,
        use_color=use_color,
    )
    should_load_sources: bool = (
        load_sources
        if load_sources is not None
        else build_effective_settings_config(discovered_inputs=discovered_inputs).auto_load_sources
    )
    if not json_output:
        progress_stream.write("\n")
        progress_stream.flush()
    external_sql_reference_resolver: object | None = resolve_external_sql_reference_resolver(
        project_dir=effective_project_dir,
        discovered_inputs=discovered_inputs,
    )
    pipeline_result: CompilePipelineResult
    if discovered_inputs.project_config.settings.virtual_environments:
        pipeline_result = run_virtual_plan_pipeline(
            project_dir=effective_project_dir,
            discovered_inputs=discovered_inputs,
            adapter=adapter,
            selected_target=selected_target,
            no_sql_validation=no_sql_validation,
            defer_sources_to=defer_sources_to,
            cursor_overrides=cursor_overrides,
            full_refresh=full_refresh,
            virtual_environment_name=virtual_env,
            include_stale_upstreams=include_stale_upstreams,
            changes_only=not effective_force,
            auto_load_sources=should_load_sources,
            include_python=include_python,
            select=select,
            exclude=exclude,
            connection_config=connection_config,
            cli_vars=cli_vars,
            on_connection_start=connection_progress.on_connection_start,
            on_connection_complete=connection_progress.on_connection_complete,
            on_connection_error=connection_progress.on_connection_error,
            on_progress=planning_progress.on_progress,
            external_sql_reference_resolver=external_sql_reference_resolver,
        )
    else:
        pipeline_result = run_compile_pipeline(
            discovered_inputs=discovered_inputs,
            adapter=adapter,
            selected_target=selected_target,
            no_sql_validation=no_sql_validation,
            defer_to=defer_to,
            defer_sources_to=defer_sources_to,
            cursor_overrides=cursor_overrides,
            full_refresh=full_refresh,
            changes_only=not effective_force,
            auto_load_sources=should_load_sources,
            select=select,
            exclude=exclude,
            connection_config=connection_config,
            cli_vars=cli_vars,
            on_connection_start=connection_progress.on_connection_start,
            on_connection_complete=connection_progress.on_connection_complete,
            on_connection_error=connection_progress.on_connection_error,
            on_progress=planning_progress.on_progress,
            external_sql_reference_resolver=external_sql_reference_resolver,
            resolve_python_run_selectors=include_python,
        )

    plan_output: PlanOutput = pipeline_result.plan_output

    if json_output:
        print(
            format_plan_json(
                plan_output,
                python_plan_entries=pipeline_result.python_plan_entries,
            )
        )
        return 0

    display_options: DisplayOptions = DisplayOptions(
        max_entries_per_section=None if verbose else 50
    )
    print(
        "\n"
        + format_plan(
            plan_output,
            full_refresh=full_refresh,
            use_color=use_color,
            display_options=display_options,
            python_plan_entries=pipeline_result.python_plan_entries,
        )
        + "\n"
    )
    return 0
