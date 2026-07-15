"""CLI rollback command entry point."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.planning.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.cli.commands._helpers.rollback.models import RollbackCommandRequest
from sqlbuild.cli.commands._helpers.rollback.output import format_rollback_output
from sqlbuild.cli.commands._helpers.runtime.adapters import resolve_adapter
from sqlbuild.cli.commands._helpers.runtime.connection import (
    resolve_project_connection_config,
)
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cli.progress.classes.connection_progress_reporter import ConnectionProgressReporter
from sqlbuild.cli.progress.classes.planning_progress_reporter import PlanningProgressReporter
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.presentation.main.supports_color import supports_color
from sqlbuild.runtime.contracts.models import ConnectionHooks
from sqlbuild.spec.resolution.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)
from sqlbuild.spec.resolution.main.resolve_target_name import resolve_target_name
from sqlbuild.virtual.executor.main.rollback import run_virtual_rollback
from sqlbuild.virtual.executor.models import RollbackOptions


def run_rollback(request: RollbackCommandRequest) -> int:
    """Execute the rollback command."""

    cli_vars: dict[str, object] | None = request.cli_vars
    effective_project_dir: Path = (
        request.project_dir if request.project_dir is not None else Path.cwd()
    )
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    if not discovered_inputs.project_config.settings.virtual_environments:
        raise CliUserError("rollback requires virtual_environments = true", code="C245")
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
    resolved_target_name: str | None = resolve_target_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_target=None,
    )
    virtual_environment_name: str | None = request.virtual_environment or resolved_target_name
    if virtual_environment_name is None:
        raise CliUserError("rollback requires --virtual-env or a default environment", code="C246")
    use_color: bool = not request.no_color and supports_color()
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
        options=RollbackOptions(
            checkpoint_id=request.checkpoint_id,
            select=request.select,
            exclude=request.exclude,
            allow_partial_rollback=request.allow_partial_rollback,
            include_stale_upstreams=request.include_stale_upstreams,
            no_sql_validation=request.no_sql_validation,
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
        format_rollback_output(
            virtual_environment=virtual_environment_name,
            checkpoint_id=restored_checkpoint_id,
            rolled_back_models=rolled_back_models,
            status=status.value,
            verbose=request.verbose,
            use_color=use_color,
        )
    )
    return 0
