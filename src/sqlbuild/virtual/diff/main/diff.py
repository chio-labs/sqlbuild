"""Virtual-mode diff entrypoint."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.executor.diff.main.execute import execute_diff
from sqlbuild.executor.diff.models import DiffExecutionResult
from sqlbuild.shared.types import ExternalSqlReferenceResolver
from sqlbuild.virtual.diff.helpers.diff import (
    filter_models_with_changed_virtual_refs,
    is_working_environment,
    non_finalized_target_names,
    read_physical_relations_for_refs,
    resolve_virtual_diff_model_names,
    rewrite_project_to_physical_relations,
)
from sqlbuild.virtual.planner.main.semantics import build_virtual_plan_semantics
from sqlbuild.virtual.planner.models import VirtualPlanSemantics
from sqlbuild.virtual.state.main.environments.runtime import build_state_runtime
from sqlbuild.virtual.state.models import (
    ModelVersionRecord,
    PhysicalRelationRecord,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentRecord,
)


def run_virtual_diff(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    from_virtual_environment_name: str,
    to_virtual_environment_name: str,
    no_sql_validation: bool = False,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    schema_only: bool = False,
    bounded: str | None = None,
    collect_samples: bool = False,
    max_column_examples: int = 20,
    max_row_only_examples: int = 20,
    allow_partial_diff: bool = False,
    cli_vars: dict[str, object] | None = None,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
    on_progress: Callable[[str], None] | None = None,
    on_connection_start: Callable[[int], None] | None = None,
    on_connection_complete: Callable[[int, float], None] | None = None,
    on_connection_error: Callable[[int, float], None] | None = None,
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

    compile_start: float = time.perf_counter()
    if on_progress is not None:
        on_progress("Compiling project...")
    graph: ProjectGraph = build_project_graph(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        cli_vars=cli_vars,
        external_sql_reference_resolver=external_sql_reference_resolver,
    )
    if on_progress is not None:
        on_progress(f"Compiled project. ({time.perf_counter() - compile_start:.2f}s)")
    selected_names: tuple[str, ...] = resolve_virtual_diff_model_names(
        graph=graph,
        select=select,
        exclude=exclude,
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
        from_environment: VirtualEnvironmentRecord | None = backend.get_virtual_environment(
            state_connection,
            schema=config.schema,
            virtual_environment_name=from_virtual_environment_name,
        )
        to_environment: VirtualEnvironmentRecord | None = backend.get_virtual_environment(
            state_connection,
            schema=config.schema,
            virtual_environment_name=to_virtual_environment_name,
        )
        from_refs: tuple[VirtualEnvironmentModelRefRecord, ...] = (
            backend.get_virtual_environment_model_refs(
                state_connection,
                schema=config.schema,
                virtual_environment_name=from_virtual_environment_name,
            )
        )
        to_refs: tuple[VirtualEnvironmentModelRefRecord, ...] = (
            backend.get_virtual_environment_model_refs(
                state_connection,
                schema=config.schema,
                virtual_environment_name=to_virtual_environment_name,
            )
        )
        if not from_refs:
            raise PlannerInputError(
                f"unknown virtual environment '{from_virtual_environment_name}'",
                code="S011",
            )
        if not to_refs:
            raise PlannerInputError(
                f"unknown virtual environment '{to_virtual_environment_name}'",
                code="S011",
            )
        from_model_versions: dict[str, ModelVersionRecord | None] = _read_model_versions(
            backend=backend,
            state_connection=state_connection,
            schema=config.schema,
            refs=from_refs,
        )
        to_model_versions: dict[str, ModelVersionRecord | None] = _read_model_versions(
            backend=backend,
            state_connection=state_connection,
            schema=config.schema,
            refs=to_refs,
        )
        from_semantics: VirtualPlanSemantics = build_virtual_plan_semantics(
            graph=graph,
            bound_refs=from_refs,
            bound_model_versions=from_model_versions,
        )
        to_semantics: VirtualPlanSemantics = build_virtual_plan_semantics(
            graph=graph,
            bound_refs=to_refs,
            bound_model_versions=to_model_versions,
        )
        if not select and not allow_partial_diff:
            non_finalized: tuple[str, ...] = non_finalized_target_names(
                (
                    (from_virtual_environment_name, from_environment),
                    (to_virtual_environment_name, to_environment),
                )
            )
            if non_finalized:
                raise PlannerInputError(
                    "whole-VDE virtual diff requires finalized VDEs; non-finalized VDEs: "
                    + ", ".join(non_finalized),
                    code="S012",
                    help="Re-run with --allow-partial-diff to inspect a working VDE.",
                )
        from_relations: dict[str, PhysicalRelationRecord] = read_physical_relations_for_refs(
            backend=backend,
            state_connection=state_connection,
            schema=config.schema,
            refs=from_refs,
        )
        to_relations: dict[str, PhysicalRelationRecord] = read_physical_relations_for_refs(
            backend=backend,
            state_connection=state_connection,
            schema=config.schema,
            refs=to_refs,
        )
        if on_progress is not None:
            on_progress(f"Inspected virtual state. ({time.perf_counter() - inspect_start:.2f}s)")
    finally:
        backend.close(state_connection)

    compared_names: tuple[str, ...]
    skipped_names: tuple[str, ...]
    compared_names, skipped_names = filter_models_with_changed_virtual_refs(
        selected_names=selected_names,
        from_refs=from_refs,
        to_refs=to_refs,
    )
    missing: tuple[str, ...] = tuple(
        name for name in compared_names if name not in from_relations or name not in to_relations
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
            from_semantics.stale_model_names,
            to_semantics.stale_model_names,
            is_working_environment(from_environment),
            is_working_environment(to_environment),
        )

    left_project: CompiledProject = rewrite_project_to_physical_relations(
        adapter=adapter,
        project=graph.project,
        relations=from_relations,
    )
    right_project: CompiledProject = rewrite_project_to_physical_relations(
        adapter=adapter,
        project=graph.project,
        relations=to_relations,
    )
    started_at: float = time.perf_counter()
    if on_connection_start is not None:
        on_connection_start(1)
    connection: Any
    try:
        connection = adapter.connect(connection_config)
    except Exception:
        if on_connection_error is not None:
            on_connection_error(1, time.perf_counter() - started_at)
        raise
    if on_connection_complete is not None:
        on_connection_complete(1, time.perf_counter() - started_at)
    try:
        result: DiffExecutionResult = execute_diff(
            adapter=adapter,
            connection=connection,
            left_project=left_project,
            right_project=right_project,
            selected_names=compared_names,
            schema_only=schema_only,
            bounded=bounded,
            collect_samples=collect_samples,
            max_column_examples=max_column_examples,
            max_row_only_examples=max_row_only_examples,
        )
    finally:
        adapter.close(connection)
    return (
        result,
        selected_names,
        skipped_names,
        from_semantics.stale_model_names,
        to_semantics.stale_model_names,
        is_working_environment(from_environment),
        is_working_environment(to_environment),
    )


def _read_model_versions(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    refs: tuple[VirtualEnvironmentModelRefRecord, ...],
) -> dict[str, ModelVersionRecord | None]:
    return {
        ref.model_name: backend.get_model_version(
            state_connection,
            schema=schema,
            model_name=ref.model_name,
            version_hash=ref.version_hash,
        )
        for ref in refs
    }
