"""Virtual promote helper functions."""

from __future__ import annotations

from typing import Any

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.types import WorkSelectionPolicy
from sqlbuild.virtual.executor._helpers.seeding import read_seed_physical_relations
from sqlbuild.virtual.executor.models import (
    PromoteEnvironmentState,
    PromoteRefUpdate,
    PromoteResolution,
    PromoteSelection,
    PromoteSemantics,
    VirtualEnvironmentPhysicalRelations,
)
from sqlbuild.virtual.planner.main._selection import resolve_virtual_plan_model_selection
from sqlbuild.virtual.planner.main._semantics import build_virtual_plan_semantics
from sqlbuild.virtual.planner.main._upstreams import build_virtual_stale_required_upstream_closure
from sqlbuild.virtual.planner.models import VirtualPlanSemantics
from sqlbuild.virtual.state.main.checkpoints._checkpoints import (
    create_finalized_virtual_environment_checkpoint,
)
from sqlbuild.virtual.state.models import (
    FunctionVersionRecord,
    ModelVersionRecord,
    PhysicalRelationRecord,
    SourceFreshnessRecord,
    VirtualEnvironmentFunctionRefRecord,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentNodeRefRecord,
    VirtualEnvironmentRecord,
    VirtualEnvironmentSeedRefRecord,
)
from sqlbuild.virtual.state.types import VirtualEnvironmentStatus


def read_promote_environment_state(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    from_virtual_environment_name: str,
    to_virtual_environment_name: str,
) -> PromoteEnvironmentState:
    """Read bound refs and environment records for one promote run."""

    source_refs: tuple[VirtualEnvironmentModelRefRecord, ...] = (
        backend.get_virtual_environment_model_refs(
            connection=state_connection,
            schema=schema,
            virtual_environment_name=from_virtual_environment_name,
        )
    )
    target_refs: tuple[VirtualEnvironmentModelRefRecord, ...] = (
        backend.get_virtual_environment_model_refs(
            connection=state_connection,
            schema=schema,
            virtual_environment_name=to_virtual_environment_name,
        )
    )
    source_function_refs: tuple[VirtualEnvironmentFunctionRefRecord, ...] = (
        backend.get_virtual_environment_function_refs(
            connection=state_connection,
            schema=schema,
            virtual_environment_name=from_virtual_environment_name,
        )
    )
    from_seed_refs: tuple[VirtualEnvironmentSeedRefRecord, ...] = (
        backend.get_virtual_environment_seed_refs(
            connection=state_connection,
            schema=schema,
            virtual_environment_name=from_virtual_environment_name,
        )
    )
    to_seed_refs: tuple[VirtualEnvironmentSeedRefRecord, ...] = (
        backend.get_virtual_environment_seed_refs(
            connection=state_connection,
            schema=schema,
            virtual_environment_name=to_virtual_environment_name,
        )
    )
    if not source_refs:
        raise PlannerInputError(
            f"unknown source virtual environment '{from_virtual_environment_name}'",
            code="S011",
        )
    source_environment: VirtualEnvironmentRecord | None = backend.get_virtual_environment(
        connection=state_connection,
        schema=schema,
        virtual_environment_name=from_virtual_environment_name,
    )
    if (
        source_environment is not None
        and source_environment.status == VirtualEnvironmentStatus.DETACHED
    ):
        raise PlannerInputError(
            f"source virtual environment '{from_virtual_environment_name}' is detached",
            code="S028",
        )
    target_environment: VirtualEnvironmentRecord | None = backend.get_virtual_environment(
        connection=state_connection,
        schema=schema,
        virtual_environment_name=to_virtual_environment_name,
    )
    if (
        target_environment is not None
        and target_environment.status == VirtualEnvironmentStatus.DETACHED
    ):
        raise PlannerInputError(
            f"target virtual environment '{to_virtual_environment_name}' is detached",
            code="S028",
        )
    source_freshness_records: tuple[SourceFreshnessRecord, ...] = (
        backend.get_virtual_environment_source_freshness(
            connection=state_connection,
            schema=schema,
            virtual_environment_name=from_virtual_environment_name,
        )
    )
    target_freshness_records: tuple[SourceFreshnessRecord, ...] = (
        backend.get_virtual_environment_source_freshness(
            connection=state_connection,
            schema=schema,
            virtual_environment_name=to_virtual_environment_name,
        )
    )
    return PromoteEnvironmentState(
        source_refs=source_refs,
        target_refs=target_refs,
        source_function_refs=source_function_refs,
        from_seed_refs=from_seed_refs,
        to_seed_refs=to_seed_refs,
        source_environment=source_environment,
        target_environment=target_environment,
        source_freshness_records=source_freshness_records,
        target_freshness_records=target_freshness_records,
    )


def build_promote_semantics(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    graph: ProjectGraph,
    environment_state: PromoteEnvironmentState,
) -> PromoteSemantics:
    """Build source and target virtual plan semantics from bound refs."""

    source_versions: dict[str, ModelVersionRecord | None] = _read_model_versions(
        backend=backend,
        state_connection=state_connection,
        schema=schema,
        refs=environment_state.source_refs,
    )
    target_versions: dict[str, ModelVersionRecord | None] = _read_model_versions(
        backend=backend,
        state_connection=state_connection,
        schema=schema,
        refs=environment_state.target_refs,
    )
    source_semantics: VirtualPlanSemantics = build_virtual_plan_semantics(
        graph=graph,
        bound_refs=environment_state.source_refs,
        bound_model_versions=source_versions,
        bound_seed_refs=environment_state.from_seed_refs,
        source_freshness_records=environment_state.source_freshness_records,
    )
    target_semantics: VirtualPlanSemantics = build_virtual_plan_semantics(
        graph=graph,
        bound_refs=environment_state.target_refs,
        bound_model_versions=target_versions,
        bound_seed_refs=environment_state.to_seed_refs,
        source_freshness_records=environment_state.target_freshness_records,
    )
    return PromoteSemantics(source=source_semantics, target=target_semantics)


def resolve_promote_selection(
    *,
    graph: ProjectGraph,
    environment_state: PromoteEnvironmentState,
    source_semantics: VirtualPlanSemantics,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    include_stale_upstreams: bool,
) -> PromoteSelection:
    """Resolve and validate the promote model and seed selection scope."""

    selected_model_names: tuple[str, ...] = resolve_virtual_plan_model_selection(
        graph=graph,
        select=select,
        exclude=exclude,
        default_selection=tuple(model.name for model in graph.project.models),
        stale_model_names=source_semantics.stale_model_names,
        include_stale_upstreams=include_stale_upstreams,
        work_selection_policy=WorkSelectionPolicy.ALL_SELECTED,
    )
    if not select:
        selected_model_names = tuple(model.name for model in graph.project.models)
        if (
            environment_state.source_environment is None
            or environment_state.source_environment.status != VirtualEnvironmentStatus.FINALIZED
        ):
            raise PlannerInputError(
                "whole-VDE promotion requires a finalized source virtual environment",
                code="S018",
                help="Use --select for a coherent partial promotion from a working source VDE.",
            )
    selected_seed_names: tuple[str, ...] = selected_upstream_seed_names(
        graph=graph,
        selected_model_names=selected_model_names,
        all_seed_names=tuple(seed.name for seed in graph.project.seeds),
        include_all=not select,
    )
    source_ref_map: dict[str, str] = {
        ref.model_name: ref.version_hash for ref in environment_state.source_refs
    }
    from_seed_ref_map: dict[str, str] = {
        ref.seed_name: ref.version_hash for ref in environment_state.from_seed_refs
    }
    missing_source_refs: tuple[str, ...] = tuple(
        model_name for model_name in selected_model_names if model_name not in source_ref_map
    )
    if missing_source_refs:
        raise PlannerInputError(
            "source virtual environment is missing selected refs: "
            + ", ".join(missing_source_refs),
            code="S015",
        )
    missing_from_seed_refs: tuple[str, ...] = tuple(
        seed_name for seed_name in selected_seed_names if seed_name not in from_seed_ref_map
    )
    if missing_from_seed_refs:
        raise PlannerInputError(
            "source virtual environment is missing selected seed refs: "
            + ", ".join(missing_from_seed_refs),
            code="S015",
        )
    return PromoteSelection(
        selected_model_names=selected_model_names,
        selected_seed_names=selected_seed_names,
        source_ref_map=source_ref_map,
        from_seed_ref_map=from_seed_ref_map,
    )


def resolve_promote_final_refs(
    *,
    graph: ProjectGraph,
    environment_state: PromoteEnvironmentState,
    selection: PromoteSelection,
    target_semantics: VirtualPlanSemantics,
    select: tuple[str, ...],
    include_stale_upstreams: bool,
    allow_partial_promotion: bool,
) -> PromoteResolution:
    """Resolve final ref hashes, staleness, and target status for the promotion."""

    selected_model_names: tuple[str, ...] = selection.selected_model_names
    selected_seed_names: tuple[str, ...] = selection.selected_seed_names
    final_version_hashes: dict[str, str] = {
        ref.model_name: ref.version_hash for ref in environment_state.target_refs
    }
    final_seed_hashes: dict[str, str] = {
        ref.seed_name: ref.version_hash for ref in environment_state.to_seed_refs
    }
    for model_name in selected_model_names:
        final_version_hashes[model_name] = selection.source_ref_map[model_name]
    for seed_name in selected_seed_names:
        final_seed_hashes[seed_name] = selection.from_seed_ref_map[seed_name]
    stale_after: tuple[str, ...] = _stale_models_after_promotion(
        graph=graph,
        final_version_hashes=final_version_hashes,
        expected_version_hashes=target_semantics.expected_version_hashes,
    )
    if not select:
        stale_after = ()
    stale_upstreams: tuple[str, ...] = build_virtual_stale_required_upstream_closure(
        graph=graph,
        selected_model_names=selected_model_names,
        stale_model_names=stale_after,
    )
    if stale_upstreams and not include_stale_upstreams:
        raise PlannerInputError(
            "selected promotion scope is missing stale required upstream models: "
            + ", ".join(stale_upstreams),
            code="S016",
            help="Re-run with --include-stale-upstreams to add required upstream refs.",
        )
    if stale_upstreams:
        selected_model_names = tuple(sorted({*selected_model_names, *stale_upstreams}))
        selected_seed_names = selected_upstream_seed_names(
            graph=graph,
            selected_model_names=selected_model_names,
            all_seed_names=tuple(seed.name for seed in graph.project.seeds),
            include_all=False,
        )
        for model_name in stale_upstreams:
            final_version_hashes[model_name] = selection.source_ref_map[model_name]
        for seed_name in selected_seed_names:
            if seed_name not in selection.from_seed_ref_map:
                raise PlannerInputError(
                    "source virtual environment is missing selected seed refs: " + seed_name,
                    code="S015",
                )
            final_seed_hashes[seed_name] = selection.from_seed_ref_map[seed_name]
        stale_after = _stale_models_after_promotion(
            graph=graph,
            final_version_hashes=final_version_hashes,
            expected_version_hashes=target_semantics.expected_version_hashes,
        )
    if stale_after and not allow_partial_promotion:
        raise PlannerInputError(
            "promotion would leave target virtual environment working; remaining stale models: "
            + ", ".join(stale_after),
            code="S017",
            help="Re-run with --allow-partial-promotion to accept a working target VDE.",
        )
    status: VirtualEnvironmentStatus = (
        VirtualEnvironmentStatus.FINALIZED if not stale_after else VirtualEnvironmentStatus.ACTIVE
    )
    return PromoteResolution(
        selected_model_names=selected_model_names,
        selected_seed_names=selected_seed_names,
        final_version_hashes=final_version_hashes,
        final_seed_hashes=final_seed_hashes,
        stale_after=stale_after,
        status=status,
    )


def build_promote_ref_update(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    from_virtual_environment_name: str,
    to_virtual_environment_name: str,
    resolution: PromoteResolution,
    source_function_refs: tuple[VirtualEnvironmentFunctionRefRecord, ...],
    select: tuple[str, ...],
) -> PromoteRefUpdate:
    """Build the target environment record and replacement ref groups."""

    virtual_environment_record: VirtualEnvironmentRecord = VirtualEnvironmentRecord(
        virtual_environment_name=to_virtual_environment_name,
        status=resolution.status,
        baseline_virtual_environment_name=from_virtual_environment_name,
    )
    refs: tuple[VirtualEnvironmentModelRefRecord, ...] = tuple(
        VirtualEnvironmentModelRefRecord(
            virtual_environment_name=to_virtual_environment_name,
            model_name=model_name,
            version_hash=version_hash,
        )
        for model_name, version_hash in sorted(resolution.final_version_hashes.items())
    )
    seed_refs: tuple[VirtualEnvironmentSeedRefRecord, ...] = tuple(
        VirtualEnvironmentSeedRefRecord(
            virtual_environment_name=to_virtual_environment_name,
            seed_name=seed_name,
            version_hash=version_hash,
        )
        for seed_name, version_hash in sorted(resolution.final_seed_hashes.items())
    )
    function_refs: tuple[VirtualEnvironmentFunctionRefRecord, ...] = ()
    function_versions: dict[str, FunctionVersionRecord] = {}
    if not select:
        function_refs = tuple(
            VirtualEnvironmentFunctionRefRecord(
                virtual_environment_name=to_virtual_environment_name,
                node_type=ref.node_type,
                function_name=ref.function_name,
                version_hash=ref.version_hash,
            )
            for ref in source_function_refs
        )
        for ref in function_refs:
            function_version: FunctionVersionRecord | None = backend.get_function_version(
                connection=state_connection,
                schema=schema,
                function_name=ref.function_name,
                version_hash=ref.version_hash,
            )
            if function_version is not None:
                function_versions[ref.function_name] = function_version
    refs_by_node_type: dict[str, tuple[VirtualEnvironmentNodeRefRecord, ...]] = {
        "model": tuple(
            VirtualEnvironmentNodeRefRecord(
                virtual_environment_name=ref.virtual_environment_name,
                node_type="model",
                node_name=ref.model_name,
                version_hash=ref.version_hash,
            )
            for ref in refs
        ),
        "seed": tuple(
            VirtualEnvironmentNodeRefRecord(
                virtual_environment_name=ref.virtual_environment_name,
                node_type="seed",
                node_name=ref.seed_name,
                version_hash=ref.version_hash,
            )
            for ref in seed_refs
        ),
    }
    if not select:
        refs_by_node_type["udf"] = tuple(
            VirtualEnvironmentNodeRefRecord(
                virtual_environment_name=ref.virtual_environment_name,
                node_type=ref.node_type,
                node_name=ref.function_name,
                version_hash=ref.version_hash,
            )
            for ref in function_refs
            if ref.node_type == CompiledResourceType.UDF
        )
        refs_by_node_type["table_fn"] = tuple(
            VirtualEnvironmentNodeRefRecord(
                virtual_environment_name=ref.virtual_environment_name,
                node_type=ref.node_type,
                node_name=ref.function_name,
                version_hash=ref.version_hash,
            )
            for ref in function_refs
            if ref.node_type == CompiledResourceType.TABLE_FN
        )
    return PromoteRefUpdate(
        virtual_environment_record=virtual_environment_record,
        refs=refs,
        seed_refs=seed_refs,
        function_refs=function_refs,
        function_versions=function_versions,
        refs_by_node_type=refs_by_node_type,
    )


def write_promote_environment_update(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    to_virtual_environment_name: str,
    update: PromoteRefUpdate,
) -> None:
    """Persist the promoted environment record, ref groups, and checkpoint."""

    backend.upsert_virtual_environment_and_replace_node_ref_groups(
        connection=state_connection,
        schema=schema,
        record=update.virtual_environment_record,
        refs_by_node_type=update.refs_by_node_type,
    )
    finalized: bool = update.virtual_environment_record.status == VirtualEnvironmentStatus.FINALIZED
    if finalized and update.refs:
        create_finalized_virtual_environment_checkpoint(
            backend=backend,
            connection=state_connection,
            schema=schema,
            virtual_environment_name=to_virtual_environment_name,
            refs=update.refs,
            function_refs=update.function_refs,
            seed_refs=update.seed_refs,
        )


def read_promote_physical_relations(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    update: PromoteRefUpdate,
) -> VirtualEnvironmentPhysicalRelations:
    """Read tracked physical relations backing the promoted refs."""

    model_relations: dict[str, PhysicalRelationRecord] = _read_physical_relations(
        backend=backend,
        state_connection=state_connection,
        schema=schema,
        refs=update.refs,
    )
    seed_relations: dict[str, PhysicalRelationRecord] = read_seed_physical_relations(
        backend=backend,
        state_connection=state_connection,
        schema=schema,
        seed_version_hashes={ref.seed_name: ref.version_hash for ref in update.seed_refs},
    )
    return VirtualEnvironmentPhysicalRelations(
        model_relations=model_relations,
        seed_relations=seed_relations,
    )


def _stale_models_after_promotion(
    *,
    graph: ProjectGraph,
    final_version_hashes: dict[str, str],
    expected_version_hashes: dict[str, str],
) -> tuple[str, ...]:
    return tuple(
        model.name
        for model in graph.project.models
        if final_version_hashes.get(model.name) != expected_version_hashes.get(model.name)
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
            connection=state_connection,
            schema=schema,
            model_name=ref.model_name,
            version_hash=ref.version_hash,
        )
        for ref in refs
    }


def _read_physical_relations(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    refs: tuple[VirtualEnvironmentModelRefRecord, ...],
) -> dict[str, PhysicalRelationRecord]:
    relations: dict[str, PhysicalRelationRecord] = {}
    for ref in refs:
        relation: PhysicalRelationRecord | None = backend.get_physical_relation(
            connection=state_connection,
            schema=schema,
            model_name=ref.model_name,
            version_hash=ref.version_hash,
        )
        if relation is not None:
            relations[ref.model_name] = relation
    return relations


def selected_upstream_seed_names(
    *,
    graph: ProjectGraph,
    selected_model_names: tuple[str, ...],
    all_seed_names: tuple[str, ...],
    include_all: bool,
) -> tuple[str, ...]:
    """Resolve seed names reachable upstream from the selected models."""

    if include_all:
        return all_seed_names
    selected: set[str] = set()
    pending: list[CompiledObjectKey] = [
        model.key for model in graph.project.models if model.name in selected_model_names
    ]
    seen: set[CompiledObjectKey] = set()
    while pending:
        key: CompiledObjectKey = pending.pop()
        if key in seen:
            continue
        seen.add(key)
        upstream_key: CompiledObjectKey
        for upstream_key in graph.upstream_deps.get(key, ()):
            if upstream_key.resource_type == CompiledResourceType.SEED:
                selected.add(upstream_key.name)
                continue
            pending.append(upstream_key)
    return tuple(sorted(selected))
