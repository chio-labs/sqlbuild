"""CLI rollback command entry point."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.helpers.rollback.output import format_rollback_output
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.cli.commands.main.shared.helpers.config.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection.core import (
    resolve_project_connection_config,
)
from sqlbuild.cli.commands.main.shared.helpers.connection.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.cli.commands.main.shared.helpers.progress.connection import ConnectionProgressReporter
from sqlbuild.cli.commands.main.shared.helpers.progress.planning import PlanningProgressReporter
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.shared.helpers.colors import supports_color
from sqlbuild.spec.models.project import resolve_effective_adapter_name
from sqlbuild.spec.models.targets import resolve_target_name
from sqlbuild.virtual.executor.main.rollback import run_virtual_rollback


def run_rollback(
    project_dir: Path | None,
    no_color: bool,
    no_sql_validation: bool,
    virtual_environment: str | None,
    verbose: bool = False,
    checkpoint_id: str | None = None,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    allow_partial_rollback: bool = False,
    include_stale_upstreams: bool = False,
    cli_vars: dict[str, object] | None = None,
) -> int:
    """Execute the rollback command."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    if not discovered_inputs.project_config.settings.virtual_environments:
        raise CliUserError("rollback requires virtual_environments = true", code="C245")
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
    resolved_target_name: str | None = resolve_target_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_target=None,
    )
    virtual_environment_name: str | None = virtual_environment or resolved_target_name
    if virtual_environment_name is None:
        raise CliUserError("rollback requires --virtual-env or a default environment", code="C246")
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
    restored_checkpoint_id, rolled_back_models, status = run_virtual_rollback(
        project_dir=effective_project_dir,
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        connection_config=connection_config,
        virtual_environment_name=virtual_environment_name,
        checkpoint_id=checkpoint_id,
        select=select,
        exclude=exclude,
        allow_partial_rollback=allow_partial_rollback,
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
        format_rollback_output(
            virtual_environment=virtual_environment_name,
            checkpoint_id=restored_checkpoint_id,
            rolled_back_models=rolled_back_models,
            status=status.value,
            verbose=verbose,
            use_color=use_color,
        )
    )
    return 0
