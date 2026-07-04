"""Build command invocation resolution phase."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.helpers.build.models import BuildCommandRequest, BuildInvocation
from sqlbuild.cli.commands.shared.exceptions import CliUserError
from sqlbuild.cli.commands.shared.helpers.config.adapters import resolve_adapter
from sqlbuild.cli.commands.shared.helpers.config.mode import (
    enforce_no_defer_to_in_virtual_mode,
    enforce_virtual_only_flags_in_virtual_mode,
)
from sqlbuild.cli.commands.shared.helpers.connection.core import (
    resolve_project_connection_config,
)
from sqlbuild.cli.commands.shared.helpers.progress.connection import (
    ConnectionProgressReporter,
)
from sqlbuild.cli.commands.shared.helpers.progress.planning import PlanningProgressReporter
from sqlbuild.compiler.compile.main.effective_settings import build_effective_settings_config
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.shared.helpers.output.colors import supports_color
from sqlbuild.spec.models.project import TargetConfig, resolve_effective_adapter_name
from sqlbuild.spec.models.targets import (
    resolve_effective_force,
    resolve_target_config,
    resolve_target_name,
)


def resolve_build_invocation(*, request: BuildCommandRequest) -> BuildInvocation:
    """Resolve discovery, validations, adapter, connection, and reporters for build."""

    effective_project_dir: Path = (
        request.project_dir if request.project_dir is not None else Path.cwd()
    )
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    effective_defer_clone_from: str | None = _resolve_defer_clone_from(
        discovered_inputs=discovered_inputs,
        selected_target=request.selected_target,
        cli_defer_clone_from=request.defer_clone_from,
    )
    if request.defer_to is not None and effective_defer_clone_from is not None:
        raise CliUserError("--defer-clone-from cannot be used with --defer-to", code="C408")
    if (
        discovered_inputs.project_config.settings.virtual_environments
        and effective_defer_clone_from is not None
    ):
        raise CliUserError(
            "build does not support --defer-clone-from when virtual_environments = true",
            code="C412",
        )
    if discovered_inputs.project_config.settings.virtual_environments and request.manifest:
        raise CliUserError(
            "build does not support --manifest when virtual_environments = true",
            code="C264",
        )
    effective_force: bool = resolve_effective_force(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_target=request.selected_target,
        cli_force=request.force,
    )
    enforce_no_defer_to_in_virtual_mode(
        discovered_inputs=discovered_inputs,
        command_name="build",
        defer_to=request.defer_to,
    )
    enforce_virtual_only_flags_in_virtual_mode(
        discovered_inputs=discovered_inputs,
        command_name="build",
        virtual_env=request.virtual_env,
        include_stale_upstreams=request.include_stale_upstreams,
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
        selected_target=request.selected_target,
        cli_vars=request.cli_vars,
    )
    use_color: bool = not request.no_color and supports_color()
    progress_stream: TextIO = sys.stderr if request.debug or request.json_output else sys.stdout
    should_load_sources: bool = request.reload_sources or (
        request.load_sources
        if request.load_sources is not None
        else build_effective_settings_config(discovered_inputs=discovered_inputs).auto_load_sources
    )
    return BuildInvocation(
        effective_project_dir=effective_project_dir,
        discovered_inputs=discovered_inputs,
        effective_defer_clone_from=effective_defer_clone_from,
        effective_force=effective_force,
        adapter_name=adapter_name,
        adapter=adapter,
        connection_config=connection_config,
        use_color=use_color,
        progress_stream=progress_stream,
        connection_progress=ConnectionProgressReporter(
            adapter_name=adapter_name,
            stream=progress_stream,
            use_color=use_color,
        ),
        planning_progress=PlanningProgressReporter(
            stream=progress_stream,
            use_color=use_color,
        ),
        should_load_sources=should_load_sources,
        virtual_mode=bool(discovered_inputs.project_config.settings.virtual_environments),
    )


def _resolve_defer_clone_from(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    selected_target: str | None,
    cli_defer_clone_from: str | None,
) -> str | None:
    if cli_defer_clone_from is not None:
        return cli_defer_clone_from
    target_name: str | None = resolve_target_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_target=selected_target,
    )
    if target_name is None:
        return None
    target_config: TargetConfig = resolve_target_config(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        target_name=target_name,
    )
    return target_config.defer_clone_from
