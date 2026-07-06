"""Helpers for direct build defer-clone prephase."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.helpers.build.models import (
    BuildCommandRequest,
    BuildInvocation,
    DeferClonePrephaseInputs,
    DeferClonePrephaseOutcome,
    DeferClonePrephaseOutputContext,
)
from sqlbuild.cli.commands.shared.exceptions import CliUserError
from sqlbuild.cli.commands.shared.helpers.connection.core import (
    resolve_target_connection_config,
)
from sqlbuild.cli.commands.shared.helpers.connection.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.clone import run_clone_pipeline
from sqlbuild.compiler.pipeline.main.compiled_project import build_compiled_project
from sqlbuild.compiler.pipeline.models import ClonePipelineResult
from sqlbuild.compiler.planner.main.planning.scope import build_planner_scope
from sqlbuild.compiler.planner.models import PlannerScope
from sqlbuild.executor.clone.main.execute import execute_clone
from sqlbuild.executor.clone.main.fingerprinting import copy_clone_fingerprints
from sqlbuild.executor.clone.main.run_prephase_clone_stream import run_prephase_clone_stream
from sqlbuild.executor.clone.models import CloneExecutionResult
from sqlbuild.executor.clone.types import CloneStatus
from sqlbuild.shared.helpers.graph.algorithms import (
    resolve_clone_boundary,
    resolve_skipped_view_chain,
)


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
) -> tuple[CompiledProject, tuple[str, ...], tuple[str, ...]]:
    """Resolve out-of-selection clone boundaries and the view chain to rebuild over them."""

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
    return (
        project,
        defer_clone_boundary_selectors(scope=scope),
        defer_clone_view_chain_selectors(scope=scope),
    )


def _scope_is_view(*, scope: PlannerScope, key: CompiledObjectKey) -> bool:
    model: CompiledModel | None = scope.models_by_name.get(key.name)
    if model is None:
        return False
    return str(model.config.values.get("materialized", "view")).lower() == "view"


def _scope_is_clonable(key: CompiledObjectKey) -> bool:
    return key.resource_type in {CompiledResourceType.MODEL, CompiledResourceType.SEED}


def defer_clone_boundary_selectors(*, scope: PlannerScope) -> tuple[str, ...]:
    """Return clone selectors for the first non-view model/seed upstreams outside selection."""

    boundary_keys: frozenset[CompiledObjectKey] = resolve_clone_boundary(
        selected=scope.selected_keys,
        upstream=scope.upstream_deps,
        is_clonable=_scope_is_clonable,
        is_view=lambda key: _scope_is_view(scope=scope, key=key),
    )
    return tuple(sorted(key.name for key in boundary_keys))


def defer_clone_view_chain_selectors(*, scope: PlannerScope) -> tuple[str, ...]:
    """Return out-of-selection view models that must rebuild over cloned boundaries."""

    view_keys: frozenset[CompiledObjectKey] = resolve_skipped_view_chain(
        selected=scope.selected_keys,
        upstream=scope.upstream_deps,
        is_clonable=_scope_is_clonable,
        is_view=lambda key: _scope_is_view(scope=scope, key=key),
    )
    return tuple(sorted(key.name for key in view_keys))


def run_defer_clone_boundary_prephase(
    *,
    request: BuildCommandRequest,
    invocation: BuildInvocation,
    origin_target_name: str,
) -> DeferClonePrephaseOutcome:
    """Resolve defer-clone boundaries and clone them before build planning."""

    cloned_project: CompiledProject
    boundary_selectors: tuple[str, ...]
    view_chain_selectors: tuple[str, ...]
    cloned_project, boundary_selectors, view_chain_selectors = build_defer_clone_boundary_selectors(
        discovered_inputs=invocation.discovered_inputs,
        adapter=invocation.adapter,
        selected_target=request.selected_target,
        no_sql_validation=request.no_sql_validation,
        select=request.select,
        exclude=request.exclude,
        cli_vars=request.cli_vars,
        project_dir=invocation.effective_project_dir,
        auto_load_sources=invocation.should_load_sources,
    )
    run_defer_clone_prephase(
        inputs=DeferClonePrephaseInputs(
            discovered_inputs=invocation.discovered_inputs,
            adapter=invocation.adapter,
            origin_target_name=origin_target_name,
            destination_target_name=cloned_project.effective_target_name,
            no_sql_validation=request.no_sql_validation,
            select=(*boundary_selectors, *view_chain_selectors),
            caused_by_names=request.select,
            cli_vars=request.cli_vars,
            connection_config=invocation.connection_config,
            project_dir=invocation.effective_project_dir,
        ),
        output_context=DeferClonePrephaseOutputContext(
            on_progress=invocation.planning_progress.on_progress,
            progress_stream=invocation.progress_stream,
            use_color=invocation.use_color,
        ),
    )
    return DeferClonePrephaseOutcome(
        destination_target_name=cloned_project.effective_target_name,
        boundary_selectors=boundary_selectors,
        view_chain_selectors=view_chain_selectors,
    )


def run_defer_clone_prephase(
    *,
    inputs: DeferClonePrephaseInputs,
    output_context: DeferClonePrephaseOutputContext | None = None,
) -> None:
    """Clone selected boundary relations from origin before build planning."""

    context: DeferClonePrephaseOutputContext = (
        output_context if output_context is not None else DeferClonePrephaseOutputContext()
    )
    discovered_inputs: DiscoveredProjectInputs = inputs.discovered_inputs
    adapter: BaseAdapter = inputs.adapter
    origin_target_name: str = inputs.origin_target_name
    destination_target_name: str | None = inputs.destination_target_name
    cli_vars: dict[str, object] | None = inputs.cli_vars
    project_dir: Path = inputs.project_dir
    on_progress: Any = context.on_progress
    if not inputs.select:
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
    destination_connection: Any = adapter.connect(inputs.connection_config)
    try:
        clone_pipeline: ClonePipelineResult = run_clone_pipeline(
            discovered_inputs=discovered_inputs,
            adapter=adapter,
            origin_target_name=origin_target_name,
            destination_target_name=destination_target_name,
            no_sql_validation=inputs.no_sql_validation,
            select=inputs.select,
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

        def run_clone(on_item: Any) -> CloneExecutionResult:
            return execute_clone(
                origin_model_entries=clone_pipeline.origin_model_entries,
                destination_model_entries=clone_pipeline.destination_model_entries,
                origin_seed_entries=clone_pipeline.origin_seed_entries,
                destination_seed_entries=clone_pipeline.destination_seed_entries,
                adapter=adapter,
                origin_connection=origin_connection,
                destination_connection=destination_connection,
                hard_copy=False,
                on_item=on_item,
            )

        result: CloneExecutionResult = (
            run_clone(None)
            if context.progress_stream is None
            else run_prephase_clone_stream(
                stream=context.progress_stream,
                title="defer clone",
                caused_by_names=inputs.caused_by_names,
                use_color=context.use_color,
                run_clone=run_clone,
            )
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
    finally:
        adapter.close(origin_connection)
        adapter.close(destination_connection)
