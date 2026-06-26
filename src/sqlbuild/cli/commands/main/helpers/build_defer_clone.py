"""Helpers for direct build defer-clone prephase."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.cli.commands.main.shared.helpers.connection.core import (
    resolve_target_connection_config,
)
from sqlbuild.cli.commands.main.shared.helpers.connection.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.compiler.compile.models.core import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.clone import run_clone_pipeline
from sqlbuild.compiler.pipeline.main.compiled_project import build_compiled_project
from sqlbuild.compiler.pipeline.models import ClonePipelineResult
from sqlbuild.compiler.planner.main.scope import build_planner_scope
from sqlbuild.compiler.planner.models import PlannerScope
from sqlbuild.executor.clone.main.execute import execute_clone
from sqlbuild.executor.clone.main.fingerprinting import copy_clone_fingerprints
from sqlbuild.executor.clone.models import CloneExecutionResult
from sqlbuild.executor.clone.types import CloneStatus


def build_defer_clone_boundary_selectors(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    selected_target: str | None,
    no_sql_validation: bool,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    cli_vars: dict[str, object] | None,
    project_dir: Path,
    auto_load_sources: bool,
) -> tuple[CompiledProject, tuple[str, ...]]:
    """Compile and resolve out-of-selection boundary resources to clone."""

    project: CompiledProject = build_compiled_project(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        selected_target=selected_target,
        no_sql_validation=no_sql_validation,
        cli_vars=cli_vars,
        external_sql_reference_resolver=resolve_external_sql_reference_resolver(
            project_dir=project_dir,
            discovered_inputs=discovered_inputs,
        ),
    )
    scope: PlannerScope = build_planner_scope(
        project=project,
        select=select,
        exclude=exclude,
        auto_load_sources=auto_load_sources,
    )
    return project, defer_clone_boundary_selectors(scope=scope)


def defer_clone_boundary_selectors(*, scope: PlannerScope) -> tuple[str, ...]:
    """Return clone selectors for model/seed upstreams outside the selected scope."""

    boundary_keys: set[CompiledObjectKey] = set()
    selected_keys: frozenset[CompiledObjectKey] = scope.selected_keys

    def visit(key: CompiledObjectKey) -> None:
        upstream_key: CompiledObjectKey
        for upstream_key in scope.upstream_deps.get(key, ()):
            if upstream_key in selected_keys:
                visit(upstream_key)
                continue
            if upstream_key.resource_type in {
                CompiledResourceType.MODEL,
                CompiledResourceType.SEED,
            }:
                boundary_keys.add(upstream_key)
            visit(upstream_key)

    selected_key: CompiledObjectKey
    for selected_key in selected_keys:
        visit(selected_key)
    return tuple(sorted(key.name for key in boundary_keys))


def run_defer_clone_prephase(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    origin_target_name: str,
    destination_target_name: str | None,
    no_sql_validation: bool,
    select: tuple[str, ...],
    cli_vars: dict[str, object] | None,
    connection_config: dict[str, object],
    project_dir: Path,
    on_progress: Any,
) -> None:
    """Clone selected boundary relations from origin before build planning."""

    if not select:
        return
    if destination_target_name is None:
        raise CliUserError("--defer-clone-from requires an active target", code="C409")
    if origin_target_name == destination_target_name:
        raise CliUserError(
            f"Cannot defer-clone from the current target '{origin_target_name}'",
            code="C410",
        )
    if on_progress is not None:
        on_progress("Preparing defer clone plan...")
    start: float = time.monotonic()
    origin_connection: Any = adapter.connect(
        resolve_target_connection_config(
            discovered_inputs=discovered_inputs,
            project_dir=project_dir,
            target_name=origin_target_name,
            cli_vars=cli_vars,
        )
    )
    destination_connection: Any = adapter.connect(connection_config)
    try:
        clone_pipeline: ClonePipelineResult = run_clone_pipeline(
            discovered_inputs=discovered_inputs,
            adapter=adapter,
            origin_target_name=origin_target_name,
            destination_target_name=destination_target_name,
            no_sql_validation=no_sql_validation,
            select=select,
            exclude=(),
            cli_vars=cli_vars,
            destination_connection=destination_connection,
            external_sql_reference_resolver=resolve_external_sql_reference_resolver(
                project_dir=project_dir,
                discovered_inputs=discovered_inputs,
            ),
        )
        if on_progress is not None:
            on_progress(f"Prepared defer clone plan. ({time.monotonic() - start:.2f}s)")
            on_progress("Cloning deferred boundary relations...")
        clone_start: float = time.monotonic()
        result: CloneExecutionResult = execute_clone(
            origin_model_entries=clone_pipeline.origin_model_entries,
            destination_model_entries=clone_pipeline.destination_model_entries,
            origin_seed_entries=clone_pipeline.origin_seed_entries,
            destination_seed_entries=clone_pipeline.destination_seed_entries,
            adapter=adapter,
            origin_connection=origin_connection,
            destination_connection=destination_connection,
            hard_copy=False,
        )
        failed_or_warning_items: tuple[str, ...] = tuple(
            f"{item.name}: {item.message or item.action.value}"
            for item in result.item_results
            if item.status in {CloneStatus.FAILED, CloneStatus.WARNING}
        )
        if failed_or_warning_items:
            raise CliUserError(
                "failed to clone one or more deferred boundary relations: "
                + "; ".join(failed_or_warning_items),
                code="C411",
            )
        copy_clone_fingerprints(
            result=result,
            origin_model_entries=clone_pipeline.origin_model_entries,
            destination_model_entries=clone_pipeline.destination_model_entries,
            origin_seed_entries=clone_pipeline.origin_seed_entries,
            destination_seed_entries=clone_pipeline.destination_seed_entries,
            adapter=adapter,
            origin_connection=origin_connection,
            destination_connection=destination_connection,
            run_id=clone_pipeline.destination_project.run_id,
            query_change_tracking=clone_pipeline.destination_project.settings.query_change_tracking,
        )
        if on_progress is not None:
            on_progress(
                f"Cloned deferred boundary relations. ({time.monotonic() - clone_start:.2f}s)"
            )
    finally:
        adapter.close(origin_connection)
        adapter.close(destination_connection)
