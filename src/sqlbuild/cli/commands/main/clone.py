"""CLI clone command entry point."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.helpers.clone.output import (
    is_clone_success,
    render_clone_output,
)
from sqlbuild.cli.commands.main.helpers.clone.validation import validate_clone_request
from sqlbuild.cli.commands.main.helpers.clone.virtual_output import (
    is_virtual_clone_success,
    render_virtual_clone_output,
)
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import (
    resolve_target_connection_config,
)
from sqlbuild.cli.commands.main.shared.helpers.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.clone import run_clone_pipeline
from sqlbuild.compiler.pipeline.models import ClonePipelineResult
from sqlbuild.compiler.planner.models import ModelPlanEntry, SeedPlanEntry
from sqlbuild.executor.clone.main.execute import execute_clone
from sqlbuild.executor.clone.models import CloneExecutionResult
from sqlbuild.shared.helpers.colors import supports_color
from sqlbuild.spec.models.project import resolve_effective_adapter_name
from sqlbuild.virtual.executor.main.clone import run_virtual_clone
from sqlbuild.virtual.executor.models import VirtualCloneResult


def run_clone(
    project_dir: Path | None,
    no_color: bool,
    no_sql_validation: bool,
    from_target: str,
    to_target: str,
    hard_copy: bool,
    virtual_env: str | None = None,
    skip_locked: bool = False,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    verbose: bool = False,
    cli_vars: dict[str, object] | None = None,
) -> int:
    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    validate_clone_request(
        discovered_inputs=discovered_inputs,
        from_target=from_target,
        to_target=to_target,
    )
    effective_adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(
        effective_adapter_name, project_dir=effective_project_dir
    )

    source_connection_config: dict[str, object] = resolve_target_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=effective_project_dir,
        target_name=from_target,
        cli_vars=cli_vars,
    )
    target_connection_config: dict[str, object] = resolve_target_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=effective_project_dir,
        target_name=to_target,
        cli_vars=cli_vars,
    )
    if discovered_inputs.project_config.settings.virtual_environments:
        result: VirtualCloneResult = run_virtual_clone(
            project_dir=effective_project_dir,
            discovered_inputs=discovered_inputs,
            adapter=adapter,
            from_target=from_target,
            to_target=to_target,
            source_connection_config=source_connection_config,
            target_connection_config=target_connection_config,
            virtual_environment_name=virtual_env,
            skip_locked=skip_locked,
            no_sql_validation=no_sql_validation,
            select=select,
            exclude=exclude,
            cli_vars=cli_vars,
            external_sql_reference_resolver=resolve_external_sql_reference_resolver(
                project_dir=effective_project_dir,
                discovered_inputs=discovered_inputs,
            ),
        )
        render_virtual_clone_output(
            result=result,
            use_color=not no_color and supports_color(),
            verbose=verbose,
        )
        return 0 if is_virtual_clone_success(result) else 1

    source_connection: Any = adapter.connect(source_connection_config)
    target_connection: Any = adapter.connect(target_connection_config)
    try:
        clone_pipeline: ClonePipelineResult = run_clone_pipeline(
            discovered_inputs=discovered_inputs,
            adapter=adapter,
            from_target=from_target,
            to_target=to_target,
            no_sql_validation=no_sql_validation,
            select=select,
            exclude=exclude,
            cli_vars=cli_vars,
            target_connection=target_connection,
            external_sql_reference_resolver=resolve_external_sql_reference_resolver(
                project_dir=effective_project_dir,
                discovered_inputs=discovered_inputs,
            ),
        )
        target_model_entries: tuple[ModelPlanEntry, ...] = clone_pipeline.target_model_entries
        target_seed_entries: tuple[SeedPlanEntry, ...] = clone_pipeline.target_seed_entries
        if not target_model_entries and not target_seed_entries:
            raise CliUserError("no cloneable resources found in the selected scope", code="C407")

        result: CloneExecutionResult = execute_clone(
            source_model_entries=clone_pipeline.source_model_entries,
            target_model_entries=target_model_entries,
            source_seed_entries=clone_pipeline.source_seed_entries,
            target_seed_entries=target_seed_entries,
            adapter=adapter,
            source_connection=source_connection,
            target_connection=target_connection,
            hard_copy=hard_copy,
        )
    finally:
        adapter.close(source_connection)
        adapter.close(target_connection)

    render_clone_output(
        result=result,
        from_target=from_target,
        to_target=to_target,
        use_color=not no_color and supports_color(),
    )
    return 0 if is_clone_success(result) else 1
