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
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_connection_config
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.clone import run_clone_pipeline
from sqlbuild.compiler.pipeline.models import ClonePipelineResult
from sqlbuild.compiler.planner.models import ModelPlanEntry, SeedPlanEntry
from sqlbuild.executor.clone.main.execute import execute_clone
from sqlbuild.executor.clone.models import CloneExecutionResult
from sqlbuild.shared.helpers.colors import supports_color


def run_clone(
    project_dir: Path | None,
    no_color: bool,
    no_sql_validation: bool,
    from_environment: str,
    to_environment: str,
    hard_copy: bool,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
) -> int:
    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    validate_clone_request(
        discovered_inputs=discovered_inputs,
        from_environment=from_environment,
        to_environment=to_environment,
    )
    adapter: BaseAdapter = resolve_adapter(discovered_inputs.project_config.adapter)

    source_connection_config: dict[str, object] = resolve_connection_config(
        raw_config={
            **discovered_inputs.project_config.connection,
            **discovered_inputs.project_config.environments[from_environment].connection,
        },
        project_dir=effective_project_dir,
    )
    target_connection_config: dict[str, object] = resolve_connection_config(
        raw_config={
            **discovered_inputs.project_config.connection,
            **discovered_inputs.project_config.environments[to_environment].connection,
        },
        project_dir=effective_project_dir,
    )
    source_connection: Any = adapter.connect(source_connection_config)
    target_connection: Any = adapter.connect(target_connection_config)
    try:
        clone_pipeline: ClonePipelineResult = run_clone_pipeline(
            discovered_inputs=discovered_inputs,
            adapter=adapter,
            from_environment=from_environment,
            to_environment=to_environment,
            no_sql_validation=no_sql_validation,
            select=select,
            exclude=exclude,
            target_connection=target_connection,
        )
        target_model_entries: tuple[ModelPlanEntry, ...] = clone_pipeline.target_model_entries
        target_seed_entries: tuple[SeedPlanEntry, ...] = clone_pipeline.target_seed_entries
        if not target_model_entries and not target_seed_entries:
            raise CliUserError("No cloneable resources found in the selected scope")

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
        from_environment=from_environment,
        to_environment=to_environment,
        use_color=not no_color and supports_color(),
    )
    return 0 if is_clone_success(result) else 1
