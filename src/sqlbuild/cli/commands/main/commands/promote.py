"""CLI promote command entry point."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.helpers.promote.models import PromoteCommandRequest
from sqlbuild.cli.commands.helpers.promote.output import format_promote_output
from sqlbuild.cli.commands.shared.exceptions import CliUserError
from sqlbuild.cli.commands.shared.helpers.config.adapters import resolve_adapter
from sqlbuild.cli.commands.shared.helpers.connection.core import (
    resolve_project_connection_config,
)
from sqlbuild.cli.commands.shared.helpers.connection.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.cli.commands.shared.helpers.progress.connection import (
    ConnectionProgressReporter,
)
from sqlbuild.cli.commands.shared.helpers.progress.planning import PlanningProgressReporter
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.shared.helpers.output.colors import supports_color
from sqlbuild.shared.models import ConnectionHooks
from sqlbuild.spec.models.project import resolve_effective_adapter_name
from sqlbuild.virtual.executor.main.promote import run_virtual_promote
from sqlbuild.virtual.executor.models import PromoteOptions


def run_promote(request: PromoteCommandRequest) -> int:
    """Execute the promote command."""

    project_dir: Path | None = request.project_dir
    no_color: bool = request.no_color
    no_sql_validation: bool = request.no_sql_validation
    from_virtual_environment: str = request.from_virtual_environment
    to_virtual_environment: str = request.to_virtual_environment
    select: tuple[str, ...] = request.select
    exclude: tuple[str, ...] = request.exclude
    allow_partial_promotion: bool = request.allow_partial_promotion
    include_stale_upstreams: bool = request.include_stale_upstreams
    verbose: bool = request.verbose
    cli_vars: dict[str, object] | None = request.cli_vars
    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    if not discovered_inputs.project_config.settings.virtual_environments:
        raise CliUserError("promote requires virtual_environments = true", code="C243")
    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(
        adapter_name=adapter_name, project_dir=effective_project_dir
    )
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
        options=PromoteOptions(
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
        ),
        hooks=ConnectionHooks(
            on_progress=planning_progress.on_progress,
            on_connection_start=connection_progress.on_connection_start,
            on_connection_complete=lambda connection_count, elapsed_seconds: (
                connection_progress.on_connection_complete(
                    connection_count=connection_count, elapsed_seconds=elapsed_seconds
                )
            ),
            on_connection_error=lambda connection_count, elapsed_seconds: (
                connection_progress.on_connection_error(
                    connection_count=connection_count, elapsed_seconds=elapsed_seconds
                )
            ),
        ),
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
