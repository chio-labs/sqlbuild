"""CLI clone command entry point."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.helpers.clone.output import (
    is_clone_success,
    render_clone_header,
    render_clone_item_line,
    render_clone_output,
)
from sqlbuild.cli.commands.main.helpers.clone.validation import validate_clone_request
from sqlbuild.cli.commands.main.helpers.clone.virtual_output import (
    is_virtual_clone_success,
    render_virtual_clone_output,
)
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.cli.commands.main.shared.helpers.config.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection.core import (
    resolve_target_connection_config,
)
from sqlbuild.cli.commands.main.shared.helpers.connection.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.cli.commands.main.shared.helpers.progress.planning import PlanningProgressReporter
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.operations.clone import run_clone_pipeline
from sqlbuild.compiler.pipeline.models import ClonePipelineResult
from sqlbuild.compiler.planner.models import ModelPlanEntry, SeedPlanEntry
from sqlbuild.executor.clone.main.execute import execute_clone
from sqlbuild.executor.clone.main.fingerprinting import copy_clone_fingerprints
from sqlbuild.executor.clone.models import CloneExecutionResult, CloneItemResult
from sqlbuild.shared.helpers.output.colors import supports_color
from sqlbuild.spec.models.project import resolve_effective_adapter_name
from sqlbuild.virtual.executor.main.clone import run_virtual_clone
from sqlbuild.virtual.executor.models import VirtualCloneResult


def run_clone(
    project_dir: Path | None,
    no_color: bool,
    no_sql_validation: bool,
    origin_target_name: str,
    destination_target_name: str,
    hard_copy: bool,
    virtual_env: str | None = None,
    skip_locked: bool = False,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    verbose: bool = False,
    cli_vars: dict[str, object] | None = None,
) -> int:
    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    use_color: bool = not no_color and supports_color()
    progress_stream: TextIO = sys.stdout
    progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=progress_stream,
        use_color=use_color,
    )
    progress.start("Discovering project...")
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    progress.complete("Discovered project.")
    validate_clone_request(
        discovered_inputs=discovered_inputs,
        origin_target_name=origin_target_name,
        destination_target_name=destination_target_name,
    )
    effective_adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(
        effective_adapter_name, project_dir=effective_project_dir
    )

    origin_connection_config: dict[str, object] = resolve_target_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=effective_project_dir,
        target_name=origin_target_name,
        cli_vars=cli_vars,
    )
    destination_connection_config: dict[str, object] = resolve_target_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=effective_project_dir,
        target_name=destination_target_name,
        cli_vars=cli_vars,
    )
    if discovered_inputs.project_config.settings.virtual_environments:
        progress.start("Cloning virtual environment...")
        clone_start: float = time.monotonic()
        result: VirtualCloneResult = run_virtual_clone(
            project_dir=effective_project_dir,
            discovered_inputs=discovered_inputs,
            adapter=adapter,
            origin_target_name=origin_target_name,
            destination_target_name=destination_target_name,
            origin_connection_config=origin_connection_config,
            destination_connection_config=destination_connection_config,
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
        progress.complete(f"Cloned virtual environment. ({time.monotonic() - clone_start:.2f}s)")
        progress.finish(blank_line_after=True)
        render_virtual_clone_output(
            result=result,
            use_color=use_color,
            verbose=verbose,
        )
        return 0 if is_virtual_clone_success(result) else 1

    progress.start(f"Connecting to {effective_adapter_name}...")
    connect_start: float = time.monotonic()
    origin_connection: Any = adapter.connect(origin_connection_config)
    destination_connection: Any = adapter.connect(destination_connection_config)
    progress.complete(
        f"Connected to {effective_adapter_name}. ({time.monotonic() - connect_start:.2f}s)"
    )
    try:
        progress.start("Preparing clone plan...")
        planning_start: float = time.monotonic()
        clone_pipeline: ClonePipelineResult = run_clone_pipeline(
            discovered_inputs=discovered_inputs,
            adapter=adapter,
            origin_target_name=origin_target_name,
            destination_target_name=destination_target_name,
            no_sql_validation=no_sql_validation,
            select=select,
            exclude=exclude,
            cli_vars=cli_vars,
            destination_connection=destination_connection,
            external_sql_reference_resolver=resolve_external_sql_reference_resolver(
                project_dir=effective_project_dir,
                discovered_inputs=discovered_inputs,
            ),
        )
        progress.complete(f"Prepared clone plan. ({time.monotonic() - planning_start:.2f}s)")
        destination_model_entries: tuple[ModelPlanEntry, ...] = (
            clone_pipeline.destination_model_entries
        )
        destination_seed_entries: tuple[SeedPlanEntry, ...] = (
            clone_pipeline.destination_seed_entries
        )
        if not destination_model_entries and not destination_seed_entries:
            raise CliUserError("no cloneable resources found in the selected scope", code="C407")

        progress.finish()
        clone_total: int = len(destination_model_entries) + len(destination_seed_entries)
        progress_stream.write(
            render_clone_header(
                origin_target_name=origin_target_name,
                destination_target_name=destination_target_name,
                total=clone_total,
                use_color=use_color,
            )
            + "\n"
        )
        progress_stream.flush()

        def _on_clone_item(index: int, total: int, item: CloneItemResult) -> None:
            progress_stream.write(
                render_clone_item_line(index=index, total=total, item=item, use_color=use_color)
                + "\n"
            )
            progress_stream.flush()

        clone_start = time.monotonic()
        result: CloneExecutionResult = execute_clone(
            origin_model_entries=clone_pipeline.origin_model_entries,
            destination_model_entries=destination_model_entries,
            origin_seed_entries=clone_pipeline.origin_seed_entries,
            destination_seed_entries=destination_seed_entries,
            adapter=adapter,
            origin_connection=origin_connection,
            destination_connection=destination_connection,
            hard_copy=hard_copy,
            on_item=_on_clone_item,
        )
        copy_clone_fingerprints(
            result=result,
            origin_model_entries=clone_pipeline.origin_model_entries,
            destination_model_entries=destination_model_entries,
            origin_seed_entries=clone_pipeline.origin_seed_entries,
            destination_seed_entries=destination_seed_entries,
            adapter=adapter,
            origin_connection=origin_connection,
            destination_connection=destination_connection,
            run_id=clone_pipeline.destination_project.run_id,
            query_change_tracking=clone_pipeline.destination_project.settings.query_change_tracking,
        )
        clone_elapsed: float = time.monotonic() - clone_start
    finally:
        progress.finish(blank_line_after=False)
        adapter.close(origin_connection)
        adapter.close(destination_connection)

    render_clone_output(
        result=result,
        elapsed_seconds=clone_elapsed,
        use_color=use_color,
    )
    return 0 if is_clone_success(result) else 1
