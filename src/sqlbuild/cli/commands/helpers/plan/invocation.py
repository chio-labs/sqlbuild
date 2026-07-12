"""Plan command invocation resolution phase."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from sqlbuild.cli.commands.helpers.plan.models import PlanCommandRequest, PlanInvocation
from sqlbuild.cli.commands.helpers.runtime.adapter_context import (
    resolve_adapter_connection_context,
)
from sqlbuild.cli.commands.helpers.runtime.mode_policy import (
    enforce_no_defer_to_in_virtual_mode,
    enforce_virtual_only_flags_in_virtual_mode,
)
from sqlbuild.cli.commands.helpers.runtime.models import AdapterConnectionContext
from sqlbuild.cli.progress.main.build_command_progress_reporters import (
    build_command_progress_reporters,
)
from sqlbuild.cli.progress.models import CommandProgressReporters
from sqlbuild.compiler.compile.main.effective_settings import build_effective_settings_config
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.presentation.main.supports_color import supports_color
from sqlbuild.spec.models.targets import resolve_effective_force


def resolve_plan_invocation(*, request: PlanCommandRequest) -> PlanInvocation:
    """Resolve discovery, validations, adapter, connection, and reporters for plan."""

    effective_project_dir: Path = (
        request.project_dir if request.project_dir is not None else Path.cwd()
    )
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    effective_force: bool = resolve_effective_force(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_target=request.selected_target,
        cli_force=request.force,
    )
    enforce_no_defer_to_in_virtual_mode(
        discovered_inputs=discovered_inputs,
        command_name="plan",
        defer_to=request.defer_to,
    )
    enforce_virtual_only_flags_in_virtual_mode(
        discovered_inputs=discovered_inputs,
        command_name="plan",
        virtual_env=request.virtual_env,
        include_stale_upstreams=request.include_stale_upstreams,
    )
    adapter_context: AdapterConnectionContext = resolve_adapter_connection_context(
        discovered_inputs=discovered_inputs,
        effective_project_dir=effective_project_dir,
        selected_target=request.selected_target,
        cli_vars=request.cli_vars,
    )
    use_color: bool = not request.no_color and not request.json_output and supports_color()
    progress_stream: TextIO = sys.stderr if request.json_output else sys.stdout
    reporters: CommandProgressReporters = build_command_progress_reporters(
        adapter_name=adapter_context.adapter_name,
        stream=progress_stream,
        use_color=use_color,
    )
    should_load_sources: bool = (
        request.load_sources
        if request.load_sources is not None
        else build_effective_settings_config(discovered_inputs=discovered_inputs).auto_load_sources
    )
    return PlanInvocation(
        effective_project_dir=effective_project_dir,
        discovered_inputs=discovered_inputs,
        effective_force=effective_force,
        adapter=adapter_context.adapter,
        connection_config=adapter_context.connection_config,
        use_color=use_color,
        progress_stream=progress_stream,
        connection_progress=reporters.connection,
        planning_progress=reporters.planning,
        should_load_sources=should_load_sources,
        virtual_mode=bool(discovered_inputs.project_config.settings.virtual_environments),
    )
