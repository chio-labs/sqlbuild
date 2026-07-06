"""Virtual diff helper functions."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.main.planning.selection import resolve_project_selectors
from sqlbuild.executor.diff.main.execute import execute_diff
from sqlbuild.executor.diff.models import DiffExecutionResult
from sqlbuild.virtual.diff.models import VirtualDiffState
from sqlbuild.virtual.executor.main.rewrite import rewrite_virtual_project_model_locations
from sqlbuild.virtual.planner.main.semantics import build_virtual_plan_semantics
from sqlbuild.virtual.planner.main.targets import build_virtual_destination_from_physical_relation
from sqlbuild.virtual.planner.models import VirtualPlanSemantics
from sqlbuild.virtual.state.models import (
    ModelVersionRecord,
    PhysicalRelationRecord,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentRecord,
)
from sqlbuild.virtual.state.types import VirtualEnvironmentStatus


def resolve_virtual_diff_model_names(
    *, graph: ProjectGraph, select: tuple[str, ...], exclude: tuple[str, ...]
) -> tuple[str, ...]:
    """Resolve model names selected for virtual diff."""

    if not select:
        return tuple(model.name for model in graph.project.models)
    selected_keys: frozenset[CompiledObjectKey] = resolve_project_selectors(
        select=select,
        exclude=exclude,
        all_keys=graph.all_keys,
        upstream_deps=graph.upstream_deps,
        downstream_deps=graph.downstream_deps,
        tag_index=graph.tag_index,
        path_index=graph.path_index,
    )
    return tuple(
        sorted(key.name for key in selected_keys if key.resource_type == CompiledResourceType.MODEL)
    )


def read_physical_relations_for_refs(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    refs: tuple[VirtualEnvironmentModelRefRecord, ...],
) -> dict[str, PhysicalRelationRecord]:
    """Read tracked physical relations for VDE refs."""

    relations: dict[str, PhysicalRelationRecord] = {}
    for ref in refs:
        relation: PhysicalRelationRecord | None = backend.get_physical_relation(
            state_connection,
            schema=schema,
            model_name=ref.model_name,
            version_hash=ref.version_hash,
        )
        if relation is not None:
            relations[ref.model_name] = relation
    return relations


def filter_models_with_changed_virtual_refs(
    *,
    selected_names: tuple[str, ...],
    from_refs: tuple[VirtualEnvironmentModelRefRecord, ...],
    to_refs: tuple[VirtualEnvironmentModelRefRecord, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split selected models into changed/missing refs and identical refs."""

    from_hashes: dict[str, str] = {ref.model_name: ref.version_hash for ref in from_refs}
    to_hashes: dict[str, str] = {ref.model_name: ref.version_hash for ref in to_refs}
    changed_names: list[str] = []
    skipped_names: list[str] = []
    for name in selected_names:
        from_hash: str | None = from_hashes.get(name)
        to_hash: str | None = to_hashes.get(name)
        if from_hash is not None and from_hash == to_hash:
            skipped_names.append(name)
        else:
            changed_names.append(name)
    return tuple(changed_names), tuple(skipped_names)


def rewrite_project_to_physical_relations(
    *, adapter: BaseAdapter, project: CompiledProject, relations: dict[str, PhysicalRelationRecord]
) -> CompiledProject:
    """Rewrite a project's model locations to tracked physical relations."""

    targets: dict[str, CompiledRelationLocation] = {
        model.name: build_virtual_destination_from_physical_relation(
            adapter=adapter,
            relation=relations[model.name],
            fallback_target=model.destination,
        )
        for model in project.models
        if model.name in relations
    }
    return rewrite_virtual_project_model_locations(project=project, rewritten_locations=targets)


def non_finalized_target_names(
    environments: tuple[tuple[str, VirtualEnvironmentRecord | None], ...],
) -> tuple[str, ...]:
    return tuple(
        name
        for name, environment in environments
        if environment is None or environment.status != VirtualEnvironmentStatus.FINALIZED
    )


def is_working_environment(environment: VirtualEnvironmentRecord | None) -> bool:
    return environment is None or environment.status != VirtualEnvironmentStatus.FINALIZED


def read_virtual_diff_state(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    graph: ProjectGraph,
    from_virtual_environment_name: str,
    to_virtual_environment_name: str,
    require_finalized: bool,
) -> VirtualDiffState:
    """Read refs, semantics, and physical relations for both diffed VDEs."""

    from_environment: VirtualEnvironmentRecord | None = backend.get_virtual_environment(
        state_connection,
        schema=schema,
        virtual_environment_name=from_virtual_environment_name,
    )
    to_environment: VirtualEnvironmentRecord | None = backend.get_virtual_environment(
        state_connection,
        schema=schema,
        virtual_environment_name=to_virtual_environment_name,
    )
    from_refs: tuple[VirtualEnvironmentModelRefRecord, ...] = (
        backend.get_virtual_environment_model_refs(
            state_connection,
            schema=schema,
            virtual_environment_name=from_virtual_environment_name,
        )
    )
    to_refs: tuple[VirtualEnvironmentModelRefRecord, ...] = (
        backend.get_virtual_environment_model_refs(
            state_connection,
            schema=schema,
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
    from_semantics: VirtualPlanSemantics = build_virtual_plan_semantics(
        graph=graph,
        bound_refs=from_refs,
        bound_model_versions=_read_model_versions(
            backend=backend,
            state_connection=state_connection,
            schema=schema,
            refs=from_refs,
        ),
    )
    to_semantics: VirtualPlanSemantics = build_virtual_plan_semantics(
        graph=graph,
        bound_refs=to_refs,
        bound_model_versions=_read_model_versions(
            backend=backend,
            state_connection=state_connection,
            schema=schema,
            refs=to_refs,
        ),
    )
    if require_finalized:
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
    return VirtualDiffState(
        from_environment=from_environment,
        to_environment=to_environment,
        from_refs=from_refs,
        to_refs=to_refs,
        from_semantics=from_semantics,
        to_semantics=to_semantics,
        from_relations=read_physical_relations_for_refs(
            backend=backend,
            state_connection=state_connection,
            schema=schema,
            refs=from_refs,
        ),
        to_relations=read_physical_relations_for_refs(
            backend=backend,
            state_connection=state_connection,
            schema=schema,
            refs=to_refs,
        ),
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


def execute_virtual_diff_between_relations(
    *,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    left_project: CompiledProject,
    right_project: CompiledProject,
    compared_names: tuple[str, ...],
    schema_only: bool,
    bounded: str | None,
    collect_samples: bool,
    max_column_examples: int,
    max_row_only_examples: int,
    on_connection_start: Callable[[int], None] | None,
    on_connection_complete: Callable[[int, float], None] | None,
    on_connection_error: Callable[[int, float], None] | None,
) -> DiffExecutionResult:
    """Open a warehouse connection with progress callbacks and run the diff."""

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
        return execute_diff(
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
