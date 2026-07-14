"""Virtual-mode diff entrypoint."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.executor.diff.models import DiffExecutionResult
from sqlbuild.runtime.contracts.models import ConnectionHooks
from sqlbuild.virtual.diff._helpers.diff import (
    execute_virtual_diff_between_relations,
    filter_models_with_changed_virtual_refs,
    is_working_environment,
    read_virtual_diff_state,
    resolve_virtual_diff_model_names,
    rewrite_project_to_physical_relations,
)
from sqlbuild.virtual.diff.models import VirtualDiffOptions, VirtualDiffState
from sqlbuild.virtual.state.main.environments.runtime import build_state_runtime


def run_virtual_diff(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    from_virtual_environment_name: str,
    to_virtual_environment_name: str,
    options: VirtualDiffOptions | None = None,
    hooks: ConnectionHooks | None = None,
) -> tuple[
    DiffExecutionResult,
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    bool,
    bool,
]:
    """Run a diff between two VDEs in the active physical environment."""

    resolved: VirtualDiffOptions = options if options is not None else VirtualDiffOptions()
    resolved_hooks: ConnectionHooks = hooks if hooks is not None else ConnectionHooks()
    on_progress: Callable[[str], None] | None = resolved_hooks.on_progress
    compile_start: float = time.perf_counter()
    if on_progress is not None:
        on_progress("Compiling project...")
    graph: ProjectGraph = build_project_graph(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=resolved.no_sql_validation,
        cli_vars=resolved.cli_vars,
        external_sql_reference_resolver=resolved.external_sql_reference_resolver,
    )
    if on_progress is not None:
        on_progress(f"Compiled project. ({time.perf_counter() - compile_start:.2f}s)")
    selected_names: tuple[str, ...] = resolve_virtual_diff_model_names(
        graph=graph,
        select=resolved.select,
        exclude=resolved.exclude,
    )
    if not selected_names:
        selected_names = tuple(model.name for model in graph.project.models)
    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    state_connection: Any = backend.connect(config.connection)
    try:
        inspect_start: float = time.perf_counter()
        if on_progress is not None:
            on_progress("Inspecting virtual state...")
        state: VirtualDiffState = read_virtual_diff_state(
            backend=backend,
            state_connection=state_connection,
            schema=config.schema,
            graph=graph,
            from_virtual_environment_name=from_virtual_environment_name,
            to_virtual_environment_name=to_virtual_environment_name,
            require_finalized=not resolved.select and not resolved.allow_partial_diff,
        )
        if on_progress is not None:
            on_progress(f"Inspected virtual state. ({time.perf_counter() - inspect_start:.2f}s)")
    finally:
        backend.close(state_connection)

    compared_names: tuple[str, ...]
    skipped_names: tuple[str, ...]
    compared_names, skipped_names = filter_models_with_changed_virtual_refs(
        selected_names=selected_names,
        from_refs=state.from_refs,
        to_refs=state.to_refs,
    )
    missing: tuple[str, ...] = tuple(
        name
        for name in compared_names
        if name not in state.from_relations or name not in state.to_relations
    )
    if missing:
        raise PlannerInputError(
            "virtual diff selected models missing tracked physical relations: "
            + ", ".join(missing),
            code="S013",
        )
    if not compared_names:
        return (
            DiffExecutionResult(),
            selected_names,
            skipped_names,
            state.from_semantics.stale_model_names,
            state.to_semantics.stale_model_names,
            is_working_environment(state.from_environment),
            is_working_environment(state.to_environment),
        )

    left_project: CompiledProject = rewrite_project_to_physical_relations(
        adapter=adapter,
        project=graph.project,
        relations=state.from_relations,
    )
    right_project: CompiledProject = rewrite_project_to_physical_relations(
        adapter=adapter,
        project=graph.project,
        relations=state.to_relations,
    )
    result: DiffExecutionResult = execute_virtual_diff_between_relations(
        adapter=adapter,
        connection_config=connection_config,
        left_project=left_project,
        right_project=right_project,
        compared_names=compared_names,
        options=resolved,
        hooks=resolved_hooks,
    )
    return (
        result,
        selected_names,
        skipped_names,
        state.from_semantics.stale_model_names,
        state.to_semantics.stale_model_names,
        is_working_environment(state.from_environment),
        is_working_environment(state.to_environment),
    )
