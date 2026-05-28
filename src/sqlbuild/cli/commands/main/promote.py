"""CLI promote command entry point."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.helpers.promote.output import format_promote_output
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_project_connection_config
from sqlbuild.cli.commands.main.shared.helpers.connection_progress import (
    ConnectionProgressReporter,
)
from sqlbuild.cli.commands.main.shared.helpers.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.cli.commands.main.shared.helpers.planning_progress import PlanningProgressReporter
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.shared.helpers.colors import supports_color
from sqlbuild.spec.models.project import resolve_effective_adapter_name
from sqlbuild.spec.models.types import EnvironmentMode
from sqlbuild.virtual.executor.main.promote import run_virtual_promote


def run_promote(
    project_dir: Path | None,
    no_color: bool,
    no_sql_validation: bool,
    from_virtual_environment: str,
    to_virtual_environment: str,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    allow_partial_promotion: bool = False,
    include_stale_upstreams: bool = False,
    verbose: bool = False,
    cli_vars: dict[str, object] | None = None,
) -> int:
    """Execute the promote command."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    if discovered_inputs.project_config.environment_mode != EnvironmentMode.VIRTUAL:
        raise CliUserError("promote requires environment_mode = 'virtual'", code="C243")
    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(adapter_name, project_dir=effective_project_dir)
    connection_config: dict[str, object] = resolve_project_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=effective_project_dir,
        cli_vars=cli_vars,
    )
    use_color: bool = not no_color and supports_color()
    planning_progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=sys.stdout,
        use_color=use_color,
    )
    connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        stream=sys.stdout,
        use_color=use_color,
    )
    status, promoted_models, remaining_stale = run_virtual_promote(
        project_dir=effective_project_dir,
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        connection_config=connection_config,
        from_virtual_environment_name=from_virtual_environment,
        to_virtual_environment_name=to_virtual_environment,
        select=select,
        exclude=exclude,
        allow_partial_promotion=allow_partial_promotion,
        include_stale_upstreams=include_stale_upstreams,
        no_sql_validation=no_sql_validation,
        cli_vars=cli_vars,
        external_sql_reference_resolver=resolve_external_sql_reference_resolver(
            project_dir=effective_project_dir,
            discovered_inputs=discovered_inputs,
        ),
        on_progress=planning_progress.on_progress,
        on_connection_start=connection_progress.on_connection_start,
        on_connection_complete=connection_progress.on_connection_complete,
        on_connection_error=connection_progress.on_connection_error,
    )
    print(
        format_promote_output(
            from_virtual_environment=from_virtual_environment,
            to_virtual_environment=to_virtual_environment,
            status=status,
            promoted_models=promoted_models,
            remaining_stale=remaining_stale,
            verbose=verbose,
            use_color=use_color,
        )
    )
    return 0
