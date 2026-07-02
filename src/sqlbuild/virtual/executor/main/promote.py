"""Virtual promote public entrypoint."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.types import WorkSelectionPolicy
from sqlbuild.shared.types import ExternalSqlReferenceResolver
from sqlbuild.spec.models.targets import resolve_target_config, resolve_target_name
from sqlbuild.virtual.executor.helpers.promote import (
    read_seed_physical_relations,
    selected_upstream_seed_names,
)
from sqlbuild.virtual.executor.helpers.rollback import publish_function_versions
from sqlbuild.virtual.executor.main.views import refresh_logical_vde_views
from sqlbuild.virtual.planner.main.selection import resolve_virtual_plan_model_selection
from sqlbuild.virtual.planner.main.semantics import build_virtual_plan_semantics
from sqlbuild.virtual.planner.main.upstreams import build_virtual_stale_required_upstream_closure
from sqlbuild.virtual.planner.models import VirtualPlanSemantics
from sqlbuild.virtual.state.main.checkpoints.checkpoints import (
    create_finalized_virtual_environment_checkpoint,
)
from sqlbuild.virtual.state.main.environments.record_operation import record_state_operation
from sqlbuild.virtual.state.main.environments.runtime import build_state_runtime
from sqlbuild.virtual.state.main.locks.locks import (
    acquire_virtual_environment_lease,
)
from sqlbuild.virtual.state.main.locks.release_lock import release_state_lease
from sqlbuild.virtual.state.models import (
    FunctionVersionRecord,
    ModelVersionRecord,
    PhysicalRelationRecord,
    StateLockLease,
    VirtualEnvironmentFunctionRefRecord,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentNodeRefRecord,
    VirtualEnvironmentRecord,
    VirtualEnvironmentSeedRefRecord,
)
from sqlbuild.virtual.state.types import (
    StateOperationStatus,
    StateOperationType,
    VirtualEnvironmentStatus,
)


def run_virtual_promote(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    from_virtual_environment_name: str,
    to_virtual_environment_name: str,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    allow_partial_promotion: bool = False,
    include_stale_upstreams: bool = False,
    no_sql_validation: bool = False,
    cli_vars: dict[str, object] | None = None,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
    on_progress: Callable[[str], None] | None = None,
    on_connection_start: Callable[[int], None] | None = None,
    on_connection_complete: Callable[[int, float], None] | None = None,
    on_connection_error: Callable[[int, float], None] | None = None,
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    """Promote refs from one VDE to another and refresh target views."""

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
    active_target_name: str | None = resolve_target_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_target=None,
    )
    unsuffixed_virtual_environment_name: str | None = None
    if active_target_name is not None:
        unsuffixed_virtual_environment_name = resolve_target_config(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
            target_name=active_target_name,
        ).state.unsuffixed_virtual_env
    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    state_connection: Any = backend.connect(config.connection)
    lease: StateLockLease | None = None
    operation_id: str = f"promote:{uuid.uuid4()}"
    try:
        inspect_start: float = time.perf_counter()
        if on_progress is not None:
            on_progress("Inspecting virtual state...")
        record_state_operation(
            backend,
            state_connection,
            schema=config.schema,
            operation_id=operation_id,
            operation_type=StateOperationType.PROMOTE,
            status=StateOperationStatus.RUNNING,
            action="start",
            virtual_environment_name=to_virtual_environment_name,
            message=(
                f"promote from {from_virtual_environment_name} to {to_virtual_environment_name}"
            ),
        )
        lease = acquire_virtual_environment_lease(
            backend,
            state_connection,
            schema=config.schema,
            virtual_environment_name=to_virtual_environment_name,
            owner_id=f"promote:{uuid.uuid4()}",
            ttl=timedelta(minutes=10),
        )
        if lease is None:
            raise PlannerInputError(
                f"virtual environment '{to_virtual_environment_name}' is locked",
                code="S014",
            )
        source_refs: tuple[VirtualEnvironmentModelRefRecord, ...] = (
            backend.get_virtual_environment_model_refs(
                state_connection,
                schema=config.schema,
                virtual_environment_name=from_virtual_environment_name,
            )
        )
        target_refs: tuple[VirtualEnvironmentModelRefRecord, ...] = (
            backend.get_virtual_environment_model_refs(
                state_connection,
                schema=config.schema,
                virtual_environment_name=to_virtual_environment_name,
            )
        )
        source_function_refs: tuple[VirtualEnvironmentFunctionRefRecord, ...] = (
            backend.get_virtual_environment_function_refs(
                state_connection,
                schema=config.schema,
                virtual_environment_name=from_virtual_environment_name,
            )
        )
        from_seed_refs: tuple[VirtualEnvironmentSeedRefRecord, ...] = (
            backend.get_virtual_environment_seed_refs(
                state_connection,
                schema=config.schema,
                virtual_environment_name=from_virtual_environment_name,
            )
        )
        to_seed_refs: tuple[VirtualEnvironmentSeedRefRecord, ...] = (
            backend.get_virtual_environment_seed_refs(
                state_connection,
                schema=config.schema,
                virtual_environment_name=to_virtual_environment_name,
            )
        )
        if not source_refs:
            raise PlannerInputError(
                f"unknown source virtual environment '{from_virtual_environment_name}'",
                code="S011",
            )
        source_environment: VirtualEnvironmentRecord | None = backend.get_virtual_environment(
            state_connection,
            schema=config.schema,
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
            state_connection,
            schema=config.schema,
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
        source_versions: dict[str, ModelVersionRecord | None] = _read_model_versions(
            backend=backend,
            state_connection=state_connection,
            schema=config.schema,
            refs=source_refs,
        )
        target_versions: dict[str, ModelVersionRecord | None] = _read_model_versions(
            backend=backend,
            state_connection=state_connection,
            schema=config.schema,
            refs=target_refs,
        )
        source_semantics: VirtualPlanSemantics = build_virtual_plan_semantics(
            graph=graph,
            bound_refs=source_refs,
            bound_model_versions=source_versions,
            bound_seed_refs=from_seed_refs,
        )
        target_semantics: VirtualPlanSemantics = build_virtual_plan_semantics(
            graph=graph,
            bound_refs=target_refs,
            bound_model_versions=target_versions,
            bound_seed_refs=to_seed_refs,
        )
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
                source_environment is None
                or source_environment.status != VirtualEnvironmentStatus.FINALIZED
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
        source_ref_map: dict[str, str] = {ref.model_name: ref.version_hash for ref in source_refs}
        from_seed_ref_map: dict[str, str] = {
            ref.seed_name: ref.version_hash for ref in from_seed_refs
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
        final_version_hashes: dict[str, str] = {
            ref.model_name: ref.version_hash for ref in target_refs
        }
        final_seed_hashes: dict[str, str] = {
            ref.seed_name: ref.version_hash for ref in to_seed_refs
        }
        for model_name in selected_model_names:
            final_version_hashes[model_name] = source_ref_map[model_name]
        for seed_name in selected_seed_names:
            final_seed_hashes[seed_name] = from_seed_ref_map[seed_name]
        stale_after: tuple[str, ...] = tuple(
            model.name
            for model in graph.project.models
            if final_version_hashes.get(model.name)
            != target_semantics.expected_version_hashes.get(model.name)
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
                final_version_hashes[model_name] = source_ref_map[model_name]
            for seed_name in selected_seed_names:
                if seed_name not in from_seed_ref_map:
                    raise PlannerInputError(
                        "source virtual environment is missing selected seed refs: " + seed_name,
                        code="S015",
                    )
                final_seed_hashes[seed_name] = from_seed_ref_map[seed_name]
            stale_after = tuple(
                model.name
                for model in graph.project.models
                if final_version_hashes.get(model.name)
                != target_semantics.expected_version_hashes.get(model.name)
            )
        if stale_after and not allow_partial_promotion:
            raise PlannerInputError(
                "promotion would leave target virtual environment working; remaining stale models: "
                + ", ".join(stale_after),
                code="S017",
                help="Re-run with --allow-partial-promotion to accept a working target VDE.",
            )
        status: VirtualEnvironmentStatus = (
            VirtualEnvironmentStatus.FINALIZED
            if not stale_after
            else VirtualEnvironmentStatus.ACTIVE
        )
        virtual_environment_record: VirtualEnvironmentRecord = VirtualEnvironmentRecord(
            virtual_environment_name=to_virtual_environment_name,
            status=status,
            baseline_virtual_environment_name=from_virtual_environment_name,
        )
        refs: tuple[VirtualEnvironmentModelRefRecord, ...] = tuple(
            VirtualEnvironmentModelRefRecord(
                virtual_environment_name=to_virtual_environment_name,
                model_name=model_name,
                version_hash=version_hash,
            )
            for model_name, version_hash in sorted(final_version_hashes.items())
        )
        seed_refs: tuple[VirtualEnvironmentSeedRefRecord, ...] = tuple(
            VirtualEnvironmentSeedRefRecord(
                virtual_environment_name=to_virtual_environment_name,
                seed_name=seed_name,
                version_hash=version_hash,
            )
            for seed_name, version_hash in sorted(final_seed_hashes.items())
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
                    state_connection,
                    schema=config.schema,
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
                if ref.node_type == "udf"
            )
            refs_by_node_type["table_fn"] = tuple(
                VirtualEnvironmentNodeRefRecord(
                    virtual_environment_name=ref.virtual_environment_name,
                    node_type=ref.node_type,
                    node_name=ref.function_name,
                    version_hash=ref.version_hash,
                )
                for ref in function_refs
                if ref.node_type == "table_fn"
            )
        backend.upsert_virtual_environment_and_replace_node_ref_groups(
            state_connection,
            schema=config.schema,
            record=virtual_environment_record,
            refs_by_node_type=refs_by_node_type,
        )
        if status == VirtualEnvironmentStatus.FINALIZED and refs:
            create_finalized_virtual_environment_checkpoint(
                backend,
                state_connection,
                schema=config.schema,
                virtual_environment_name=to_virtual_environment_name,
                refs=refs,
                function_refs=function_refs,
                seed_refs=seed_refs,
            )
        physical_relations: dict[str, PhysicalRelationRecord] = _read_physical_relations(
            backend=backend,
            state_connection=state_connection,
            schema=config.schema,
            refs=refs,
        )
        seed_physical_relations: dict[str, PhysicalRelationRecord] = read_seed_physical_relations(
            backend=backend,
            state_connection=state_connection,
            schema=config.schema,
            refs=seed_refs,
        )
        refresh_start: float = time.perf_counter()
        if on_progress is not None:
            on_progress("Refreshing target VDE views...")
        refresh_logical_vde_views(
            project=graph.project,
            adapter=adapter,
            connection_config=connection_config,
            virtual_environment_name=to_virtual_environment_name,
            unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
            physical_relations=physical_relations,
            seed_physical_relations=seed_physical_relations,
            on_connection_start=on_connection_start,
            on_connection_complete=on_connection_complete,
            on_connection_error=on_connection_error,
        )
        if function_versions:
            publish_function_versions(
                adapter=adapter,
                connection_config=connection_config,
                graph=graph,
                virtual_environment_name=to_virtual_environment_name,
                function_versions=function_versions,
            )
        if on_progress is not None:
            on_progress(f"Refreshed target VDE views. ({time.perf_counter() - refresh_start:.2f}s)")
        record_state_operation(
            backend,
            state_connection,
            schema=config.schema,
            operation_id=operation_id,
            operation_type=None,
            status=StateOperationStatus.SUCCEEDED,
            action="finish",
            virtual_environment_name=None,
            message=f"promoted {len(selected_model_names)} models",
        )
        if on_progress is not None:
            on_progress(f"Inspected virtual state. ({time.perf_counter() - inspect_start:.2f}s)")
    except Exception as error:
        record_state_operation(
            backend,
            state_connection,
            schema=config.schema,
            operation_id=operation_id,
            operation_type=None,
            status=StateOperationStatus.FAILED,
            action="finish",
            virtual_environment_name=None,
            message=str(error),
        )
        raise
    finally:
        if lease is not None:
            release_state_lease(
                backend,
                state_connection,
                schema=config.schema,
                lease=lease,
            )
        backend.close(state_connection)
    return status.value, selected_model_names, stale_after


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
            state_connection,
            schema=schema,
            model_name=ref.model_name,
            version_hash=ref.version_hash,
        )
        if relation is not None:
            relations[ref.model_name] = relation
    return relations
