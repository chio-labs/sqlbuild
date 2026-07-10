"""Virtual-mode build entrypoint."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import sqlbuild.executor.build.types
from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.main.relation_lookup import build_relation_lookup
from sqlbuild.adapter.shared.models import RelationInfo, StatementRecorder
from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.main.materializations import load_custom_materializations
from sqlbuild.compiler.pipeline.main.prepare_versions import (
    load_custom_prepare_version_functions,
)
from sqlbuild.compiler.pipeline.main.relation_targets import (
    build_python_relation_targets,
)
from sqlbuild.compiler.pipeline.models import ProjectGraph, PythonPlanEntry
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.main.planning.build_resources import expand_build_resource_selection
from sqlbuild.compiler.planner.main.planning.plan_entry import (
    build_plan_output_from_model_changes_phase,
)
from sqlbuild.compiler.planner.main.planning.selection import resolve_project_selectors
from sqlbuild.compiler.planner.main.planning.warehouse_snapshot import (
    build_warehouse_snapshot_phase,
)
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    ChangeDetectionResult,
    ModelChangesPlanInputs,
    ModelPlanEntry,
    PlannerScope,
    PlannerWarehouseSnapshotResult,
    PlanOutput,
)
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    ChangeKind,
    PlanAction,
    PlanReason,
    WorkSelectionPolicy,
)
from sqlbuild.compiler.python_nodes.main.graph import build_discovered_python_node_graph
from sqlbuild.compiler.python_nodes.main.run_lifecycle import build_python_sql_run_lifecycle
from sqlbuild.compiler.python_nodes.models import (
    PythonNodeGraph,
    PythonSqlRunLifecyclePlan,
    PythonSqlRunSelection,
)
from sqlbuild.compiler.python_nodes.types import PythonNodeStatus
from sqlbuild.executor.build.constants import INCREMENTAL_ACTIONS
from sqlbuild.executor.build.models import (
    BuildCallbacks,
    BuildCustomizations,
    BuildExecutionResult,
    BuildInitialState,
    BuildRuntimeParams,
    SeedExecutionResult,
)
from sqlbuild.executor.build.types import BuildStatus, ExecutionStatus
from sqlbuild.executor.custom.models import (
    MaterializationContext,
    MaterializationResult,
    PrepareVersionContext,
)
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.pipeline.main.run import run_build_pipeline
from sqlbuild.executor.python_nodes.main.ingress import run_ingress_python_loader_nodes
from sqlbuild.executor.python_nodes.main.read_side import create_read_side_python_execution_tracker
from sqlbuild.executor.python_nodes.models import (
    IngressCallbacks,
    PythonIngressLoaderExecutorResult,
    PythonNodeExecutionResult,
    PythonNodeRuntime,
)
from sqlbuild.executor.python_nodes.types import PythonIdentityRecorder
from sqlbuild.shared.helpers.identity.naming import (
    resolve_qualified_name_parts,
    resolve_relation_location_qualified_name,
)
from sqlbuild.shared.models import RelationLookup, SqlResourceRef
from sqlbuild.spec.models.project import SnapshotsConfig
from sqlbuild.spec.models.targets import resolve_target_config, resolve_target_name
from sqlbuild.virtual.executor.classes.node_result_store import VirtualNodeResultStore
from sqlbuild.virtual.executor.helpers.functions import build_function_version_record
from sqlbuild.virtual.executor.helpers.rewrite import (
    build_destination_from_physical_relation,
    build_physical_seed_destination,
    build_rewritten_model_locations,
    build_virtual_destination,
    relation_type_for_model,
    rewrite_project_function_locations,
    rewrite_project_model_locations,
    rewrite_project_seed_locations,
)
from sqlbuild.virtual.executor.helpers.seeding import seed_virtual_physical_version
from sqlbuild.virtual.executor.models import (
    VirtualBuildExecutionHooks,
    VirtualBuildHooks,
    VirtualBuildOptions,
    VirtualBuildPipelineResult,
    VirtualEnvironmentNames,
)
from sqlbuild.virtual.freshness.main.current_records import (
    build_current_virtual_source_freshness_records,
)
from sqlbuild.virtual.freshness.main.runtime_observation import (
    observe_virtual_environment_source_freshness,
)
from sqlbuild.virtual.freshness.main.runtime_persistence import (
    persist_virtual_environment_source_freshness,
)
from sqlbuild.virtual.freshness.models import SourceFreshnessRuntimeResult
from sqlbuild.virtual.planner.main.output import apply_virtual_plan_output
from sqlbuild.virtual.planner.main.python_identities import read_bound_virtual_python_identities
from sqlbuild.virtual.planner.main.python_plan_entries import build_virtual_python_plan_entries
from sqlbuild.virtual.planner.main.python_run_selection import build_virtual_python_run_selection
from sqlbuild.virtual.planner.main.selection import resolve_virtual_plan_model_selection
from sqlbuild.virtual.planner.main.semantics import (
    build_virtual_plan_semantics,
)
from sqlbuild.virtual.planner.models import VirtualPlanSemantics
from sqlbuild.virtual.shared.helpers.encoding import encode_state_text
from sqlbuild.virtual.state.main.checkpoints.checkpoints import (
    create_finalized_virtual_environment_checkpoint,
)
from sqlbuild.virtual.state.main.environments.runtime import build_state_runtime
from sqlbuild.virtual.state.main.python_identities.python_node_identity_write import (
    try_record_virtual_python_node_identity,
)
from sqlbuild.virtual.state.models import (
    FunctionVersionRecord,
    ModelVersionRecord,
    PhysicalRelationAncestryRecord,
    PhysicalRelationRecord,
    SeedVersionRecord,
    SourceFreshnessRecord,
    StateBackendConfig,
    VirtualEnvironmentFunctionRefRecord,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentNodeRefRecord,
    VirtualEnvironmentRecord,
    VirtualEnvironmentSeedRefRecord,
)
from sqlbuild.virtual.state.types import (
    ModelVersionStatus,
    PhysicalArtifactType,
    VirtualEnvironmentStatus,
)


@dataclass(frozen=True)
class _VirtualBuildRuntime:
    """Shared inputs, state runtime, and naming context for one virtual build run."""

    project_dir: Path
    discovered_inputs: DiscoveredProjectInputs
    adapter: BaseAdapter
    connection_config: dict[str, object]
    options: VirtualBuildOptions
    hooks: VirtualBuildHooks
    backend: Any
    config: StateBackendConfig
    names: VirtualEnvironmentNames


@dataclass(frozen=True)
class _VirtualBuildStateReads:
    """Bound state, semantics, and resolved selection read for one virtual build run."""

    bound_function_refs: tuple[VirtualEnvironmentFunctionRefRecord, ...]
    bound_seed_refs: tuple[VirtualEnvironmentSeedRefRecord, ...]
    semantics: VirtualPlanSemantics
    selected_model_names: tuple[str, ...]
    selected_seed_names: tuple[str, ...]
    desired_seed_version_hashes: dict[str, str]
    available_seed_physical_relations: dict[str, PhysicalRelationRecord]
    seed_load_names: tuple[str, ...]
    effective_select: tuple[str, ...]
    bound_physical_relations: dict[str, PhysicalRelationRecord]


@dataclass(frozen=True)
class _RewrittenVirtualProject:
    """Version-rewritten project and deferred relations for one virtual build run."""

    project: CompiledProject
    deferred_relations: dict[str, RelationInfo]


@dataclass(frozen=True)
class _VirtualBuildPlan:
    """Display plan and executor plan for one virtual build run."""

    plan_output: PlanOutput
    executor_plan_output: PlanOutput


@dataclass(frozen=True)
class _VirtualPythonPlan:
    """Python-node graph, lifecycle, plan entries, and relation targets for one run."""

    python_graph: PythonNodeGraph
    lifecycle_plan: PythonSqlRunLifecyclePlan
    plan_entries: tuple[PythonPlanEntry, ...]
    relation_targets: dict[SqlResourceRef, str]


@dataclass(frozen=True)
class _FunctionPersistOutcome:
    """Final function version hashes and node types persisted for one run."""

    final_function_hashes: dict[str, str]
    function_ref_node_types: dict[str, str]


@dataclass(frozen=True)
class _SeedPersistOutcome:
    """Final seed version hashes and physical relations persisted for one run."""

    final_seed_hashes: dict[str, str]
    final_seed_physical_relations: dict[str, PhysicalRelationRecord]


def run_virtual_build(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    options: VirtualBuildOptions,
    hooks: VirtualBuildHooks,
) -> VirtualBuildPipelineResult:
    """Execute a virtual-mode build."""

    graph: ProjectGraph = build_project_graph(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        selected_target=options.selected_target,
        no_sql_validation=options.no_sql_validation,
        cli_vars=options.cli_vars,
        external_sql_reference_resolver=options.external_sql_reference_resolver,
        on_progress=hooks.on_progress,
    )
    names: VirtualEnvironmentNames = _resolve_virtual_environment_names(
        discovered_inputs=discovered_inputs,
        options=options,
    )
    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    runtime: _VirtualBuildRuntime = _VirtualBuildRuntime(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        connection_config=connection_config,
        options=options,
        hooks=hooks,
        backend=backend,
        config=config,
        names=names,
    )
    reads: _VirtualBuildStateReads = _read_virtual_build_state(runtime=runtime, graph=graph)
    rewritten: _RewrittenVirtualProject = _rewrite_virtual_project(
        runtime=runtime, graph=graph, reads=reads
    )
    plan: _VirtualBuildPlan = _plan_virtual_build(
        runtime=runtime,
        graph=graph,
        project=rewritten.project,
        reads=reads,
        deferred_relations=rewritten.deferred_relations,
    )
    python_plan: _VirtualPythonPlan = _prepare_virtual_python_execution(
        runtime=runtime,
        graph=graph,
        project=rewritten.project,
        plan_output=plan.plan_output,
        selected_model_names=reads.selected_model_names,
    )
    output: PlanOutput = plan.plan_output
    entries: tuple[PythonPlanEntry, ...] = python_plan.plan_entries
    exec_hooks: VirtualBuildExecutionHooks = (
        hooks.on_plan_ready(rewritten.project, plan_output=output, python_plan_entries=entries)
        if hooks.on_plan_ready is not None
        else VirtualBuildExecutionHooks()
    )
    ingress_result: PythonIngressLoaderExecutorResult | None = _run_ingress_python_nodes(
        runtime=runtime,
        python_plan=python_plan,
        plan_output=plan.plan_output,
        project=rewritten.project,
        exec_hooks=exec_hooks,
    )
    ingress_python_results: tuple[PythonNodeExecutionResult, ...] = (
        ingress_result.python_results if ingress_result is not None else ()
    )
    ingress_load_results: tuple[LoadExecutionResult, ...] = (
        ingress_result.load_results if ingress_result is not None else ()
    )
    ingress_failed: bool = any(
        load_result.status == ExecutionStatus.FAILED for load_result in ingress_load_results
    ) or any(result.status == PythonNodeStatus.FAILED for result in ingress_python_results)
    if ingress_failed:
        result: BuildExecutionResult = BuildExecutionResult(
            status=BuildStatus.FAILED, load_results=ingress_load_results
        )
    else:
        result = _execute_virtual_build_plan(
            runtime=runtime,
            plan=plan,
            project=rewritten.project,
            python_plan=python_plan,
            reads=reads,
            exec_hooks=exec_hooks,
            ingress_load_results=ingress_load_results,
        )
    if result.status == BuildStatus.SUCCESS:
        _persist_successful_virtual_build(
            runtime=runtime,
            project=graph.project,
            reads=reads,
            plan_output=plan.executor_plan_output,
            result=result,
        )
        read_side_results: tuple[PythonNodeExecutionResult, ...] = _run_read_side_python_nodes(
            runtime=runtime,
            python_plan=python_plan,
            project=rewritten.project,
            result=result,
        )
        if any(
            python_result.status == PythonNodeStatus.FAILED for python_result in read_side_results
        ):
            result = replace(result, status=BuildStatus.FAILED)
    else:
        read_side_results = ()

    return VirtualBuildPipelineResult(
        project=rewritten.project,
        direct_plan_output=plan.plan_output,
        display_plan_output=plan.plan_output,
        execution_plan=plan.executor_plan_output,
        execution_result=result,
        virtual_environment_name=runtime.names.target_vde_name,
        python_node_results=(*ingress_python_results, *read_side_results),
    )


def _resolve_virtual_environment_names(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    options: VirtualBuildOptions,
) -> VirtualEnvironmentNames:
    physical_target_name: str | None = resolve_target_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_target=options.selected_target,
    )
    unsuffixed_virtual_environment_name: str | None = None
    if physical_target_name is not None:
        unsuffixed_virtual_environment_name = resolve_target_config(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
            target_name=physical_target_name,
        ).state.unsuffixed_virtual_env
    return VirtualEnvironmentNames(
        target_vde_name=(options.virtual_environment_name or physical_target_name or "default"),
        physical_target_name=physical_target_name,
        unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
    )


def _read_virtual_build_state(
    *,
    runtime: _VirtualBuildRuntime,
    graph: ProjectGraph,
) -> _VirtualBuildStateReads:
    backend: Any = runtime.backend
    config: StateBackendConfig = runtime.config
    options: VirtualBuildOptions = runtime.options
    target_vde_name: str = runtime.names.target_vde_name
    state_connection: Any = backend.connect(config.connection)
    try:
        bound_refs: tuple[VirtualEnvironmentModelRefRecord, ...] = _read_or_initialize_refs(
            backend=backend,
            state_connection=state_connection,
            config=config,
            target_vde_name=target_vde_name,
            baseline_vde_name=runtime.names.physical_target_name,
        )
        bound_function_refs: tuple[VirtualEnvironmentFunctionRefRecord, ...] = (
            backend.get_virtual_environment_function_refs(
                state_connection,
                schema=config.schema,
                virtual_environment_name=target_vde_name,
            )
        )
        bound_seed_refs: tuple[VirtualEnvironmentSeedRefRecord, ...] = (
            backend.get_virtual_environment_seed_refs(
                state_connection,
                schema=config.schema,
                virtual_environment_name=target_vde_name,
            )
        )
        bound_model_versions: dict[str, ModelVersionRecord | None] = _read_bound_model_versions(
            backend=backend,
            state_connection=state_connection,
            config=config,
            bound_refs=bound_refs,
        )
        source_freshness_records: tuple[SourceFreshnessRecord, ...] = (
            backend.get_virtual_environment_source_freshness(
                state_connection,
                schema=config.schema,
                virtual_environment_name=target_vde_name,
            )
        )
        prebuild_source_connection: Any = runtime.adapter.connect(runtime.connection_config)
        try:
            current_source_freshness_records: tuple[SourceFreshnessRecord, ...] = (
                build_current_virtual_source_freshness_records(
                    adapter=runtime.adapter,
                    connection=prebuild_source_connection,
                    sources=tuple(source.source_entry for source in graph.project.sources),
                    virtual_environment_name=target_vde_name,
                    observed_at=datetime.now(),
                    previous_records=source_freshness_records,
                    run_id=graph.project.run_id,
                )
            )
        finally:
            runtime.adapter.close(prebuild_source_connection)
        semantics: VirtualPlanSemantics = build_virtual_plan_semantics(
            graph=graph,
            bound_refs=bound_refs,
            bound_model_versions=bound_model_versions,
            bound_seed_refs=bound_seed_refs,
            source_freshness_records=current_source_freshness_records,
        )
        work_selection_policy: WorkSelectionPolicy = (
            WorkSelectionPolicy.STALE_ONLY
            if options.changes_only
            else WorkSelectionPolicy.ALL_SELECTED
        )
        selected_model_names: tuple[str, ...]
        selected_seed_names: tuple[str, ...] = ()
        if options.seed_only:
            selected_model_names = ()
            selected_seed_names = _resolve_virtual_seed_selection(
                graph=graph,
                select=options.select,
                exclude=options.exclude,
            )
        else:
            selected_model_names = resolve_virtual_plan_model_selection(
                graph=graph,
                select=options.select,
                exclude=options.exclude,
                default_selection=semantics.default_selection,
                stale_model_names=semantics.stale_model_names,
                include_stale_upstreams=options.include_stale_upstreams,
                work_selection_policy=work_selection_policy,
            )
            selected_seed_names = (
                semantics.stale_seed_names if not options.select and not options.exclude else ()
            )
        selected_seed_names = _include_stale_upstream_seed_names(
            graph=graph,
            selected_model_names=selected_model_names,
            selected_seed_names=selected_seed_names,
            stale_seed_names=semantics.stale_seed_names,
        )
        desired_seed_version_hashes: dict[str, str] = {
            seed_name: semantics.expected_seed_version_hashes[seed_name]
            for seed_name in selected_seed_names
            if seed_name in semantics.expected_seed_version_hashes
        }
        available_seed_physical_relations: dict[str, PhysicalRelationRecord] = (
            _read_available_seed_physical_relations(
                adapter=runtime.adapter,
                connection_config=runtime.connection_config,
                backend=backend,
                state_connection=state_connection,
                config=config,
                desired_seed_version_hashes=desired_seed_version_hashes,
            )
        )
        seed_load_names: tuple[str, ...] = tuple(
            seed_name
            for seed_name in selected_seed_names
            if seed_name not in available_seed_physical_relations
        )
        effective_select: tuple[str, ...] = _build_virtual_planner_select(
            graph=graph,
            selected_model_names=selected_model_names,
            selected_seed_names=selected_seed_names,
        )
        bound_physical_relations: dict[str, PhysicalRelationRecord] = _read_bound_relations(
            backend=backend,
            state_connection=state_connection,
            config=config,
            bound_version_hashes=semantics.bound_version_hashes,
        )
    finally:
        backend.close(state_connection)
    return _VirtualBuildStateReads(
        bound_function_refs=bound_function_refs,
        bound_seed_refs=bound_seed_refs,
        semantics=semantics,
        selected_model_names=selected_model_names,
        selected_seed_names=selected_seed_names,
        desired_seed_version_hashes=desired_seed_version_hashes,
        available_seed_physical_relations=available_seed_physical_relations,
        seed_load_names=seed_load_names,
        effective_select=effective_select,
        bound_physical_relations=bound_physical_relations,
    )


def _rewrite_virtual_project(
    *,
    runtime: _VirtualBuildRuntime,
    graph: ProjectGraph,
    reads: _VirtualBuildStateReads,
) -> _RewrittenVirtualProject:
    adapter: BaseAdapter = runtime.adapter
    semantics: VirtualPlanSemantics = reads.semantics
    selected_model_version_hashes: dict[str, str] = {
        model_name: semantics.expected_version_hashes[model_name]
        for model_name in reads.selected_model_names
        if model_name in semantics.expected_version_hashes
    }
    seed_load_version_hashes: dict[str, str] = {
        seed_name: reads.desired_seed_version_hashes[seed_name]
        for seed_name in reads.seed_load_names
        if seed_name in reads.desired_seed_version_hashes
    }
    rewritten_locations: dict[str, CompiledRelationLocation] = build_rewritten_model_locations(
        project=graph.project,
        adapter=adapter,
        selected_model_version_hashes=selected_model_version_hashes,
        bound_physical_relations=reads.bound_physical_relations,
    )
    rewritten_project: CompiledProject = rewrite_project_model_locations(
        project=graph.project,
        rewritten_locations=rewritten_locations,
    )
    rewritten_seed_locations: dict[str, CompiledRelationLocation] = {
        seed.name: build_physical_seed_destination(
            adapter=adapter,
            target=seed.destination,
            seed_name=seed.name,
            version_hash=seed_load_version_hashes[seed.name],
        )
        for seed in graph.project.seeds
        if seed.name in seed_load_version_hashes
    }
    for seed in graph.project.seeds:
        if seed.name in rewritten_seed_locations:
            continue
        if seed.name in semantics.bound_seed_version_hashes:
            rewritten_seed_locations[seed.name] = build_virtual_destination(
                adapter=adapter,
                target=seed.destination,
                virtual_environment_name=runtime.names.target_vde_name,
                unsuffixed_virtual_environment_name=(
                    runtime.names.unsuffixed_virtual_environment_name
                ),
            )
    rewritten_project = rewrite_project_seed_locations(
        project=rewritten_project,
        rewritten_locations=rewritten_seed_locations,
    )
    rewritten_project = rewrite_project_function_locations(
        project=rewritten_project,
        adapter=adapter,
        virtual_environment_name=runtime.names.target_vde_name,
        unsuffixed_virtual_environment_name=runtime.names.unsuffixed_virtual_environment_name,
    )
    deferred_relations: dict[str, RelationInfo] = {
        model_name: RelationInfo(
            database=relation.database_name,
            schema=relation.schema_name,
            name=relation.relation_name,
            relation_type=relation.relation_type,
        )
        for model_name, relation in reads.bound_physical_relations.items()
    }
    return _RewrittenVirtualProject(
        project=rewritten_project,
        deferred_relations=deferred_relations,
    )


def _plan_virtual_build(
    *,
    runtime: _VirtualBuildRuntime,
    graph: ProjectGraph,
    project: CompiledProject,
    reads: _VirtualBuildStateReads,
    deferred_relations: dict[str, RelationInfo],
) -> _VirtualBuildPlan:
    adapter: BaseAdapter = runtime.adapter
    options: VirtualBuildOptions = runtime.options
    hooks: VirtualBuildHooks = runtime.hooks
    if reads.effective_select:
        if hooks.on_connection_start is not None:
            hooks.on_connection_start(1)
        connection_start: float = time.monotonic()
        try:
            planning_connection: Any = adapter.connect(runtime.connection_config)
        except Exception:
            if hooks.on_connection_error is not None:
                hooks.on_connection_error(1, elapsed_seconds=time.monotonic() - connection_start)
            raise
        if hooks.on_connection_complete is not None:
            hooks.on_connection_complete(1, elapsed_seconds=time.monotonic() - connection_start)
        try:
            warehouse_result: PlannerWarehouseSnapshotResult = build_warehouse_snapshot_phase(
                project=project,
                adapter=adapter,
                connection=planning_connection,
                select=reads.effective_select,
                exclude=(),
                auto_load_sources=options.auto_load_sources,
                full_refresh=options.full_refresh,
                deferred_relations=deferred_relations,
                on_progress=hooks.on_progress,
            )
            plan_output: PlanOutput = build_plan_output_from_model_changes_phase(
                project=project,
                adapter=adapter,
                connection=planning_connection,
                scope=warehouse_result.scope,
                snapshot=warehouse_result.snapshot,
                model_changes=_build_virtual_model_changes(
                    project=project,
                    scope=warehouse_result.scope,
                    semantics=reads.semantics,
                    bound_physical_relations=reads.bound_physical_relations,
                    full_refresh=options.full_refresh,
                ),
                inputs=ModelChangesPlanInputs(
                    cursor_overrides=options.cursor_overrides,
                    full_refresh=options.full_refresh,
                    reload_sources=options.reload_sources,
                    project_config=runtime.discovered_inputs.project_config,
                    local_config=runtime.discovered_inputs.local_config,
                    defer_sources_to=options.defer_sources_to,
                    seed_version_hashes=reads.semantics.expected_seed_version_hashes,
                    seed_metadata_jsons=reads.semantics.seed_identity_metadata_jsons,
                    seed_plan_reasons=reads.semantics.seed_plan_reasons,
                ),
            )
        finally:
            adapter.close(planning_connection)
    else:
        plan_output = PlanOutput(
            execution_order=(),
            upstream_deps=graph.upstream_deps,
            downstream_deps=graph.downstream_deps,
            selected_keys=frozenset(),
            model_locations={
                model.name: (
                    build_destination_from_physical_relation(
                        adapter=adapter,
                        relation=reads.bound_physical_relations[model.name],
                        fallback_target=model.destination,
                    )
                    if model.name in reads.bound_physical_relations
                    else model.destination
                )
                for model in graph.project.models
            },
            function_locations={
                function.name: function.destination for function in graph.project.functions
            },
            seed_locations={seed.name: seed.destination for seed in graph.project.seeds},
            source_map={source.name: source.source_entry for source in graph.project.sources},
        )
    plan_output = apply_virtual_plan_output(
        plan_output=plan_output,
        target_name=runtime.names.target_vde_name,
        semantics=reads.semantics,
        selected_model_names=reads.selected_model_names,
    )
    return _VirtualBuildPlan(
        plan_output=plan_output,
        executor_plan_output=_build_physical_seed_load_plan_output(
            plan_output=plan_output,
            seed_load_names=reads.seed_load_names,
        ),
    )


def _prepare_virtual_python_execution(
    *,
    runtime: _VirtualBuildRuntime,
    graph: ProjectGraph,
    project: CompiledProject,
    plan_output: PlanOutput,
    selected_model_names: tuple[str, ...],
) -> _VirtualPythonPlan:
    options: VirtualBuildOptions = runtime.options
    python_graph: PythonNodeGraph = build_discovered_python_node_graph(
        discovered_inputs=runtime.discovered_inputs
    )
    python_selection: PythonSqlRunSelection = build_virtual_python_run_selection(
        discovered_inputs=runtime.discovered_inputs,
        graph=graph,
        plan_output=plan_output,
        select=options.select,
        exclude=options.exclude,
        selected_model_names=selected_model_names,
        include_python=options.include_python,
    )
    lifecycle_plan: PythonSqlRunLifecyclePlan = build_python_sql_run_lifecycle(
        selection=python_selection,
        python_graph=python_graph,
    )
    previous_python_identities: dict[tuple[str, str], Fingerprint] = (
        read_bound_virtual_python_identities(
            discovered_inputs=runtime.discovered_inputs,
            project_dir=runtime.project_dir,
            virtual_environment_name=options.virtual_environment_name,
        )
    )
    return _VirtualPythonPlan(
        python_graph=python_graph,
        lifecycle_plan=lifecycle_plan,
        plan_entries=build_virtual_python_plan_entries(
            discovered_inputs=runtime.discovered_inputs,
            selection=python_selection,
            previous_identities=previous_python_identities,
        ),
        relation_targets=build_python_relation_targets(
            adapter=runtime.adapter,
            project=project,
            plan_output=plan_output,
        ),
    )


def _build_python_identity_recorder(runtime: _VirtualBuildRuntime) -> PythonIdentityRecorder:
    def record_python_identity(identity: Any, *, _target_name: str | None) -> None:
        state_connection: Any = runtime.backend.connect(runtime.config.connection)
        try:
            try_record_virtual_python_node_identity(
                backend=runtime.backend,
                state_connection=state_connection,
                schema=runtime.config.schema,
                virtual_environment_name=runtime.names.target_vde_name,
                identity=identity,
            )
        finally:
            runtime.backend.close(state_connection)

    return record_python_identity


def _run_ingress_python_nodes(
    *,
    runtime: _VirtualBuildRuntime,
    python_plan: _VirtualPythonPlan,
    plan_output: PlanOutput,
    project: CompiledProject,
    exec_hooks: VirtualBuildExecutionHooks,
) -> PythonIngressLoaderExecutorResult | None:
    if not python_plan.lifecycle_plan.ingress_python_node_names:
        return None
    adapter: BaseAdapter = runtime.adapter
    options: VirtualBuildOptions = runtime.options
    ingress_connection: Any = adapter.connect(runtime.connection_config)
    try:
        ingress_state_connection: Any = runtime.backend.connect(runtime.config.connection)
        try:
            ingress_result_store: VirtualNodeResultStore = VirtualNodeResultStore(
                backend=runtime.backend,
                state_connection=ingress_state_connection,
                state_schema=runtime.config.schema,
                virtual_environment_name=runtime.names.target_vde_name,
                target_database=adapter.default_database(),
                target_schema=adapter.default_schema(),
            )
            return run_ingress_python_loader_nodes(
                python_graph=python_plan.python_graph,
                selected_python_names=python_plan.lifecycle_plan.ingress_python_node_names,
                loader_functions=runtime.discovered_inputs.loader_functions,
                source_map=plan_output.source_map,
                runtime=PythonNodeRuntime(
                    adapter=adapter,
                    connection_config=runtime.connection_config,
                    connection=ingress_connection,
                    run_id=project.run_id,
                    target=runtime.names.target_vde_name,
                    vars=project.effective_vars,
                    is_reload=options.reload_sources,
                    default_database=adapter.default_database(),
                    default_schema=adapter.default_schema(),
                    start_cursor_ts=options.start_cursor_ts,
                    end_cursor_ts=options.end_cursor_ts,
                    start_cursor_int=options.start_cursor_int,
                    end_cursor_int=options.end_cursor_int,
                    relation_targets=python_plan.relation_targets,
                    providers=options.providers,
                    result_store=ingress_result_store,
                ),
                callbacks=IngressCallbacks(
                    on_node_start=exec_hooks.on_node_start,
                    on_node_complete=exec_hooks.on_node_complete,
                    identity_recorder=_build_python_identity_recorder(runtime),
                ),
            )
        finally:
            runtime.backend.close(ingress_state_connection)
    finally:
        adapter.close(ingress_connection)


def _execute_virtual_build_plan(
    *,
    runtime: _VirtualBuildRuntime,
    plan: _VirtualBuildPlan,
    project: CompiledProject,
    python_plan: _VirtualPythonPlan,
    reads: _VirtualBuildStateReads,
    exec_hooks: VirtualBuildExecutionHooks,
    ingress_load_results: tuple[LoadExecutionResult, ...],
) -> BuildExecutionResult:
    options: VirtualBuildOptions = runtime.options
    custom_materializations: dict[
        str, Callable[[MaterializationContext], MaterializationResult]
    ] = load_custom_materializations(runtime.discovered_inputs.materialization_files)
    prepare_version_functions: dict[str, Callable[[PrepareVersionContext], None]] = (
        load_custom_prepare_version_functions(runtime.discovered_inputs.materialization_files)
    )
    _prepare_virtual_physical_schemas(
        adapter=runtime.adapter,
        connection_config=runtime.connection_config,
        plan_output=plan.executor_plan_output,
    )
    result: BuildExecutionResult = run_build_pipeline(
        plan=plan.executor_plan_output,
        connection_config=runtime.connection_config,
        adapter=runtime.adapter,
        settings=project.settings,
        runtime=BuildRuntimeParams(
            snapshots=options.snapshots or SnapshotsConfig(),
            allow_snapshot_schema_change=options.allow_snapshot_schema_change,
            run_id=project.run_id,
            run_tests=options.run_tests,
            run_audits=options.run_audits,
            fail_fast=options.fail_fast,
            max_concurrency=(
                options.concurrency
                if options.concurrency is not None
                else project.settings.concurrency
            ),
            loader_is_reload=options.reload_sources,
            start_cursor_ts=options.start_cursor_ts,
            end_cursor_ts=options.end_cursor_ts,
            start_cursor_int=options.start_cursor_int,
            end_cursor_int=options.end_cursor_int,
            query_change_tracking=False,
            providers=options.providers,
        ),
        callbacks=BuildCallbacks(
            on_node_start=exec_hooks.on_node_start,
            on_node_complete=exec_hooks.on_node_complete,
            on_sub_progress=exec_hooks.on_sub_progress,
            before_model_materialize=_build_before_model_materialize(
                runtime=runtime,
                reads=reads,
                run_id=project.run_id,
                prepare_version_functions=prepare_version_functions,
            ),
            python_identity_recorder=_build_python_identity_recorder(runtime),
        ),
        customizations=BuildCustomizations(
            custom_materializations=custom_materializations,
            loader_functions=_sql_loader_functions_for_lifecycle_handoff(
                discovered_inputs=runtime.discovered_inputs,
                ingress_loader_names=python_plan.lifecycle_plan.ingress_loader_names,
            ),
        ),
        initial_state=BuildInitialState(
            precompleted_keys=frozenset(
                _load_result_key(plan=plan.plan_output, result=load_result)
                for load_result in ingress_load_results
            ),
            initial_load_results=ingress_load_results,
            initial_failed_keys=frozenset(
                _load_result_key(plan=plan.plan_output, result=load_result)
                for load_result in ingress_load_results
                if load_result.status != ExecutionStatus.SUCCESS
            ),
        ),
    )
    if result.status == BuildStatus.SUCCESS and reads.available_seed_physical_relations:
        result = replace(
            result,
            seed_results=result.seed_results
            + tuple(
                SeedExecutionResult(seed_name=seed_name, status=ExecutionStatus.SKIPPED)
                for seed_name in sorted(reads.available_seed_physical_relations)
            ),
        )
    return result


def _build_before_model_materialize(
    *,
    runtime: _VirtualBuildRuntime,
    reads: _VirtualBuildStateReads,
    run_id: str,
    prepare_version_functions: dict[str, Callable[[PrepareVersionContext], None]],
) -> sqlbuild.executor.build.types.BeforeModelMaterializeCallback:
    def before_model_materialize(entry: ModelPlanEntry, *, connection: Any) -> None:
        if entry.action not in INCREMENTAL_ACTIONS and entry.action != PlanAction.CUSTOM:
            return
        parent_relation: PhysicalRelationRecord | None = reads.bound_physical_relations.get(
            entry.name
        )
        version_hash: str | None = reads.semantics.expected_version_hashes.get(entry.name)
        if (
            parent_relation is None
            or version_hash is None
            or parent_relation.version_hash == version_hash
        ):
            return
        state_connection: Any = runtime.backend.connect(runtime.config.connection)
        try:
            prepare_version: Callable[[PrepareVersionContext], None] | None = (
                prepare_version_functions.get(entry.custom_materialization_name or "")
                if entry.action == PlanAction.CUSTOM
                else None
            )
            if prepare_version is not None:
                _prepare_custom_virtual_version(
                    runtime=runtime,
                    connection=connection,
                    state_connection=state_connection,
                    entry=entry,
                    parent_relation=parent_relation,
                    version_hash=version_hash,
                    prepare_version=prepare_version,
                    run_id=run_id,
                )
            else:
                seed_virtual_physical_version(
                    adapter=runtime.adapter,
                    connection=connection,
                    backend=runtime.backend,
                    state_connection=state_connection,
                    state_schema=runtime.config.schema,
                    entry=entry,
                    parent_relation=parent_relation,
                    version_hash=version_hash,
                )
        finally:
            runtime.backend.close(state_connection)

    return before_model_materialize


def _run_read_side_python_nodes(
    *,
    runtime: _VirtualBuildRuntime,
    python_plan: _VirtualPythonPlan,
    project: CompiledProject,
    result: BuildExecutionResult,
) -> tuple[PythonNodeExecutionResult, ...]:
    if not python_plan.lifecycle_plan.read_side_python_node_names:
        return ()
    adapter: BaseAdapter = runtime.adapter
    options: VirtualBuildOptions = runtime.options
    connection: Any = adapter.connect(runtime.connection_config)
    try:
        state_connection: Any = runtime.backend.connect(runtime.config.connection)
        try:
            result_store: VirtualNodeResultStore = VirtualNodeResultStore(
                backend=runtime.backend,
                state_connection=state_connection,
                state_schema=runtime.config.schema,
                virtual_environment_name=runtime.names.target_vde_name,
                target_database=adapter.default_database(),
                target_schema=adapter.default_schema(),
            )
            tracker: Any = create_read_side_python_execution_tracker(
                python_graph=python_plan.python_graph,
                selected_python_names=python_plan.lifecycle_plan.read_side_python_node_names,
                runtime=PythonNodeRuntime(
                    adapter=adapter,
                    connection_config=runtime.connection_config,
                    connection=connection,
                    run_id=project.run_id,
                    target=runtime.names.target_vde_name,
                    vars=project.effective_vars,
                    is_reload=options.reload_sources,
                    default_database=adapter.default_database(),
                    default_schema=adapter.default_schema(),
                    relation_targets=python_plan.relation_targets,
                    start_cursor_ts=options.start_cursor_ts,
                    end_cursor_ts=options.end_cursor_ts,
                    start_cursor_int=options.start_cursor_int,
                    end_cursor_int=options.end_cursor_int,
                    providers=options.providers,
                    result_store=result_store,
                ),
                identity_recorder=_build_python_identity_recorder(runtime),
            )
            load_result: LoadExecutionResult
            for load_result in result.load_results:
                tracker.record_sql_result(load_result)
            model_result: Any
            for model_result in result.model_results:
                tracker.record_sql_result(model_result)
            tracker.dispatch_ready_python_nodes()
            tracker.finalize_unrun_python_nodes()
            return tracker.results
        finally:
            runtime.backend.close(state_connection)
    finally:
        adapter.close(connection)


def _sql_loader_functions_for_lifecycle_handoff(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    ingress_loader_names: frozenset[str],
) -> tuple[Any, ...]:
    loader_functions: frozenset[object] = frozenset(
        loader.function for loader in discovered_inputs.loader_functions
    )
    return tuple(
        replace(
            loader,
            depends_on=tuple(
                dependency
                for dependency in loader.depends_on
                if dependency in loader_functions or loader.name not in ingress_loader_names
            ),
        )
        for loader in discovered_inputs.loader_functions
    )


def _load_result_key(*, plan: PlanOutput, result: LoadExecutionResult) -> CompiledObjectKey:
    for entry in plan.source_load_entries:
        if entry.name == result.source_name:
            return entry.key
    raise PlannerInputError(
        f"No source-load plan entry found for load result '{result.source_name}'"
    )


def _prepare_virtual_physical_schemas(
    *,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    plan_output: PlanOutput,
) -> None:
    schemas: set[tuple[str | None, str]] = set()
    for entry in (*plan_output.model_entries, *plan_output.seed_entries):
        if entry.destination.schema is not None:
            schemas.add((entry.destination.database, entry.destination.schema))
    if not schemas:
        return

    connection: Any = adapter.connect(connection_config)
    recorder: StatementRecorder = StatementRecorder()
    try:
        for database, schema in sorted(schemas, key=lambda item: (item[0] or "", item[1])):
            adapter.ensure_schema(
                connection,
                database=database,
                schema=schema,
                statement_recorder=recorder,
            )
    finally:
        adapter.close(connection)


def _prepare_custom_virtual_version(
    *,
    runtime: _VirtualBuildRuntime,
    connection: Any,
    state_connection: Any,
    entry: ModelPlanEntry,
    parent_relation: PhysicalRelationRecord,
    version_hash: str,
    prepare_version: Callable[[PrepareVersionContext], None],
    run_id: str,
) -> None:
    adapter: BaseAdapter = runtime.adapter
    recorder: StatementRecorder = StatementRecorder()
    adapter.ensure_schema(
        connection,
        database=entry.destination.database,
        schema=entry.destination.schema,
        statement_recorder=recorder,
    )
    destination: str = resolve_relation_location_qualified_name(
        adapter=adapter, location=entry.destination
    )
    if adapter.relation_exists(
        connection,
        database=entry.destination.database,
        schema=entry.destination.schema,
        name=entry.destination.name,
    ):
        adapter.drop(
            connection, destination=destination, if_exists=True, statement_recorder=recorder
        )
    source: str = resolve_qualified_name_parts(
        adapter=adapter,
        database=parent_relation.database_name,
        schema=parent_relation.schema_name,
        name=parent_relation.relation_name,
    )
    prepare_version(
        PrepareVersionContext(
            adapter=adapter,
            connection=connection,
            origin_relation=source,
            destination=destination,
            destination_database=entry.destination.database,
            destination_schema=entry.destination.schema,
            destination_name=entry.destination.name,
            config=dict(entry.custom_config),
            placeholders=dict(entry.custom_placeholders),
            run_id=run_id,
            environment=runtime.names.target_vde_name,
            vars=runtime.options.cli_vars or {},
            unique_key=entry.unique_key,
            declared_columns=entry.declared_columns,
            statement_recorder=recorder,
        )
    )
    runtime.backend.upsert_physical_relation_ancestry(
        state_connection,
        schema=runtime.config.schema,
        record=PhysicalRelationAncestryRecord(
            model_name=entry.name,
            version_hash=version_hash,
            parent_model_name=parent_relation.artifact_name,
            parent_version_hash=parent_relation.version_hash,
            seed_strategy="custom_prepare_version",
        ),
    )


def _read_or_initialize_refs(
    *,
    backend: Any,
    state_connection: Any,
    config: StateBackendConfig,
    target_vde_name: str,
    baseline_vde_name: str | None,
) -> tuple[VirtualEnvironmentModelRefRecord, ...]:
    environment: VirtualEnvironmentRecord | None = backend.get_virtual_environment(
        state_connection,
        schema=config.schema,
        virtual_environment_name=target_vde_name,
    )
    if environment is not None and environment.status == VirtualEnvironmentStatus.DETACHED:
        raise PlannerInputError(
            f"virtual environment '{target_vde_name}' is detached",
            code="S028",
            help="Run state adopt again or choose a non-detached virtual environment.",
        )
    refs: tuple[VirtualEnvironmentModelRefRecord, ...] = backend.get_virtual_environment_model_refs(
        state_connection,
        schema=config.schema,
        virtual_environment_name=target_vde_name,
    )
    if refs or baseline_vde_name is None or baseline_vde_name == target_vde_name:
        return refs
    baseline_refs: tuple[VirtualEnvironmentModelRefRecord, ...] = (
        backend.get_virtual_environment_model_refs(
            state_connection,
            schema=config.schema,
            virtual_environment_name=baseline_vde_name,
        )
    )
    return tuple(
        VirtualEnvironmentModelRefRecord(
            virtual_environment_name=target_vde_name,
            model_name=ref.model_name,
            version_hash=ref.version_hash,
        )
        for ref in baseline_refs
    )


def _read_bound_model_versions(
    *,
    backend: Any,
    state_connection: Any,
    config: StateBackendConfig,
    bound_refs: tuple[VirtualEnvironmentModelRefRecord, ...],
) -> dict[str, ModelVersionRecord | None]:
    return {
        ref.model_name: backend.get_model_version(
            state_connection,
            schema=config.schema,
            model_name=ref.model_name,
            version_hash=ref.version_hash,
        )
        for ref in bound_refs
    }


def _read_bound_relations(
    *,
    backend: Any,
    state_connection: Any,
    config: StateBackendConfig,
    bound_version_hashes: dict[str, str],
) -> dict[str, PhysicalRelationRecord]:
    relations: dict[str, PhysicalRelationRecord] = {}
    for model_name, version_hash in bound_version_hashes.items():
        relation: PhysicalRelationRecord | None = backend.get_physical_relation(
            state_connection,
            schema=config.schema,
            model_name=model_name,
            version_hash=version_hash,
        )
        if relation is not None:
            relations[model_name] = relation
    return relations


def _include_stale_upstream_seed_names(
    *,
    graph: ProjectGraph,
    selected_model_names: tuple[str, ...],
    selected_seed_names: tuple[str, ...],
    stale_seed_names: tuple[str, ...],
) -> tuple[str, ...]:
    selected: set[str] = set(selected_seed_names)
    stale_seed_name_set: frozenset[str] = frozenset(stale_seed_names)
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
                if upstream_key.name in stale_seed_name_set:
                    selected.add(upstream_key.name)
                continue
            pending.append(upstream_key)
    return tuple(sorted(selected))


def _read_available_seed_physical_relations(
    *,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    backend: Any,
    state_connection: Any,
    config: StateBackendConfig,
    desired_seed_version_hashes: dict[str, str],
) -> dict[str, PhysicalRelationRecord]:
    relations: dict[str, PhysicalRelationRecord] = {}
    if not desired_seed_version_hashes:
        return relations
    records_by_seed: dict[str, PhysicalRelationRecord] = {}
    seed_name: str
    version_hash: str
    for seed_name, version_hash in desired_seed_version_hashes.items():
        relation: PhysicalRelationRecord | None = backend.get_physical_relation_for_artifact(
            state_connection,
            schema=config.schema,
            artifact_type=PhysicalArtifactType.SEED,
            artifact_name=seed_name,
            version_hash=version_hash,
        )
        if relation is not None:
            records_by_seed[seed_name] = relation
    if not records_by_seed:
        return relations
    warehouse_connection: Any = adapter.connect(connection_config)
    try:
        relation_lookup: RelationLookup = build_relation_lookup(
            adapter=adapter,
            connection=warehouse_connection,
            locations=tuple(
                (record.database_name, record.schema_name, record.relation_name)
                for record in records_by_seed.values()
            ),
        )
        for seed_name, relation in records_by_seed.items():
            if relation_lookup.exists(
                database=relation.database_name,
                schema=relation.schema_name,
                name=relation.relation_name,
            ):
                relations[seed_name] = relation
    finally:
        adapter.close(warehouse_connection)
    return relations


def _build_physical_seed_load_plan_output(
    *, plan_output: PlanOutput, seed_load_names: tuple[str, ...]
) -> PlanOutput:
    seed_load_name_set: frozenset[str] = frozenset(seed_load_names)
    selected_load_seed_keys: frozenset[CompiledObjectKey] = frozenset(
        entry.key for entry in plan_output.seed_entries if entry.name in seed_load_name_set
    )
    selected_existing_seed_keys: frozenset[CompiledObjectKey] = frozenset(
        entry.key for entry in plan_output.seed_entries if entry.name not in seed_load_name_set
    )
    return replace(
        plan_output,
        execution_order=tuple(
            key for key in plan_output.execution_order if key not in selected_existing_seed_keys
        ),
        seed_entries=tuple(
            entry for entry in plan_output.seed_entries if entry.key in selected_load_seed_keys
        ),
        selected_keys=frozenset(
            key for key in plan_output.selected_keys if key not in selected_existing_seed_keys
        ),
    )


def _persist_successful_virtual_build(
    *,
    runtime: _VirtualBuildRuntime,
    project: CompiledProject,
    reads: _VirtualBuildStateReads,
    plan_output: PlanOutput,
    result: BuildExecutionResult,
) -> None:
    semantics: VirtualPlanSemantics = reads.semantics
    names: VirtualEnvironmentNames = runtime.names
    final_version_hashes: dict[str, str] = dict(semantics.bound_version_hashes)
    successful_model_names: frozenset[str] = frozenset(
        model_result.model_name
        for model_result in result.model_results
        if model_result.status == ExecutionStatus.SUCCESS
    )
    for entry in plan_output.model_entries:
        if entry.name not in successful_model_names:
            continue
        final_version_hashes[entry.name] = semantics.expected_version_hashes[entry.name]

    state_connection: Any = runtime.backend.connect(runtime.config.connection)
    try:
        _observe_and_persist_source_freshness(
            runtime=runtime,
            state_connection=state_connection,
            project=project,
            load_results=result.load_results,
        )
        _write_model_version_records(
            runtime=runtime,
            state_connection=state_connection,
            project=project,
            plan_output=plan_output,
            semantics=semantics,
            final_version_hashes=final_version_hashes,
        )
        functions: _FunctionPersistOutcome = _persist_function_versions(
            runtime=runtime,
            state_connection=state_connection,
            plan_output=plan_output,
            bound_function_refs=reads.bound_function_refs,
        )
        seeds: _SeedPersistOutcome = _persist_seed_versions(
            runtime=runtime,
            state_connection=state_connection,
            plan_output=plan_output,
            reads=reads,
            seed_results=result.seed_results,
        )
        stale_model_after_build: tuple[str, ...] = tuple(
            model.name
            for model in project.models
            if final_version_hashes.get(model.name)
            != semantics.expected_version_hashes.get(model.name)
        )
        stale_seed_after_build: tuple[str, ...] = tuple(
            seed.name
            for seed in project.seeds
            if seeds.final_seed_hashes.get(seed.name)
            != semantics.expected_seed_version_hashes.get(seed.name)
        )
        status: VirtualEnvironmentStatus = (
            VirtualEnvironmentStatus.FINALIZED
            if not stale_model_after_build and not stale_seed_after_build
            else VirtualEnvironmentStatus.ACTIVE
        )
        virtual_environment_record: VirtualEnvironmentRecord = VirtualEnvironmentRecord(
            virtual_environment_name=names.target_vde_name,
            status=status,
            baseline_virtual_environment_name=(
                names.physical_target_name
                if names.physical_target_name != names.target_vde_name
                else None
            ),
        )
        refs: tuple[VirtualEnvironmentModelRefRecord, ...] = tuple(
            VirtualEnvironmentModelRefRecord(
                virtual_environment_name=names.target_vde_name,
                model_name=model_name,
                version_hash=version_hash,
            )
            for model_name, version_hash in sorted(final_version_hashes.items())
        )
        function_refs: tuple[VirtualEnvironmentFunctionRefRecord, ...] = tuple(
            VirtualEnvironmentFunctionRefRecord(
                virtual_environment_name=names.target_vde_name,
                node_type=functions.function_ref_node_types[function_name],
                function_name=function_name,
                version_hash=version_hash,
            )
            for function_name, version_hash in sorted(functions.final_function_hashes.items())
            if function_name in functions.function_ref_node_types
        )
        seed_refs: tuple[VirtualEnvironmentSeedRefRecord, ...] = tuple(
            VirtualEnvironmentSeedRefRecord(
                virtual_environment_name=names.target_vde_name,
                seed_name=seed_name,
                version_hash=version_hash,
            )
            for seed_name, version_hash in sorted(seeds.final_seed_hashes.items())
        )
        runtime.backend.upsert_virtual_environment_and_replace_node_ref_groups(
            state_connection,
            schema=runtime.config.schema,
            record=virtual_environment_record,
            refs_by_node_type=_build_node_ref_groups(
                refs=refs, seed_refs=seed_refs, function_refs=function_refs
            ),
        )
        if status == VirtualEnvironmentStatus.FINALIZED and refs:
            create_finalized_virtual_environment_checkpoint(
                runtime.backend,
                connection=state_connection,
                schema=runtime.config.schema,
                virtual_environment_name=names.target_vde_name,
                refs=refs,
                function_refs=function_refs,
                seed_refs=seed_refs,
            )
    finally:
        runtime.backend.close(state_connection)

    _create_logical_vde_views(
        project=project,
        adapter=runtime.adapter,
        connection_config=runtime.connection_config,
        target_vde_name=names.target_vde_name,
        unsuffixed_virtual_environment_name=names.unsuffixed_virtual_environment_name,
        plan_output=plan_output,
        final_version_hashes=final_version_hashes,
        final_seed_physical_relations=seeds.final_seed_physical_relations,
    )


def _observe_and_persist_source_freshness(
    *,
    runtime: _VirtualBuildRuntime,
    state_connection: Any,
    project: CompiledProject,
    load_results: tuple[LoadExecutionResult, ...],
) -> None:
    previous_source_freshness_records: tuple[SourceFreshnessRecord, ...] = (
        runtime.backend.get_virtual_environment_source_freshness(
            state_connection,
            schema=runtime.config.schema,
            virtual_environment_name=runtime.names.target_vde_name,
        )
    )
    source_observation_connection: Any = runtime.adapter.connect(runtime.connection_config)
    try:
        source_freshness_result: SourceFreshnessRuntimeResult = (
            observe_virtual_environment_source_freshness(
                adapter=runtime.adapter,
                connection=source_observation_connection,
                sources=tuple(source.source_entry for source in project.sources),
                virtual_environment_name=runtime.names.target_vde_name,
                observed_at=datetime.now(),
                run_id=project.run_id,
                load_results=load_results,
                previous_records=previous_source_freshness_records,
            )
        )
    finally:
        runtime.adapter.close(source_observation_connection)
    persist_virtual_environment_source_freshness(
        backend=runtime.backend,
        state_connection=state_connection,
        schema=runtime.config.schema,
        virtual_environment_name=runtime.names.target_vde_name,
        result=source_freshness_result,
    )


def _write_model_version_records(
    *,
    runtime: _VirtualBuildRuntime,
    state_connection: Any,
    project: CompiledProject,
    plan_output: PlanOutput,
    semantics: VirtualPlanSemantics,
    final_version_hashes: dict[str, str],
) -> None:
    model_entries_by_name: dict[str, Any] = {
        entry.name: entry for entry in plan_output.model_entries
    }
    model: CompiledModel
    for model in project.models:
        version_hash: str | None = final_version_hashes.get(model.name)
        if version_hash is None:
            continue
        entry: Any | None = model_entries_by_name.get(model.name)
        existing_model_version: ModelVersionRecord | None = runtime.backend.get_model_version(
            state_connection,
            schema=runtime.config.schema,
            model_name=model.name,
            version_hash=version_hash,
        )
        if existing_model_version is None:
            metadata_json: str = semantics.expected_metadata_jsons.get(model.name, "{}")
            runtime.backend.upsert_model_version(
                state_connection,
                schema=runtime.config.schema,
                record=ModelVersionRecord(
                    model_name=model.name,
                    version_hash=version_hash,
                    definition_identity_hash=semantics.expected_local_hashes.get(
                        model.name, version_hash
                    ),
                    identity_metadata_hash=hashlib.sha256(
                        metadata_json.encode("utf-8")
                    ).hexdigest(),
                    status=ModelVersionStatus.READY,
                    definition_text_b64=encode_state_text(model.query_sql),
                    identity_metadata_json_b64=encode_state_text(metadata_json),
                    compiled_sql_b64=(
                        encode_state_text(entry.resolved_sql) if entry is not None else None
                    ),
                ),
            )
        target: CompiledRelationLocation | None = entry.destination if entry is not None else None
        if target is not None:
            existing_physical_relation: PhysicalRelationRecord | None = (
                runtime.backend.get_physical_relation(
                    state_connection,
                    schema=runtime.config.schema,
                    model_name=model.name,
                    version_hash=version_hash,
                )
            )
            if existing_physical_relation is None:
                runtime.backend.upsert_physical_relation(
                    state_connection,
                    schema=runtime.config.schema,
                    record=PhysicalRelationRecord(
                        artifact_type=PhysicalArtifactType.MODEL,
                        artifact_name=model.name,
                        version_hash=version_hash,
                        database_name=target.database,
                        schema_name=target.schema or "",
                        relation_name=target.name,
                        relation_type=relation_type_for_model(
                            str(model.config.values.get("materialized", "table"))
                        ),
                    ),
                )


def _persist_function_versions(
    *,
    runtime: _VirtualBuildRuntime,
    state_connection: Any,
    plan_output: PlanOutput,
    bound_function_refs: tuple[VirtualEnvironmentFunctionRefRecord, ...],
) -> _FunctionPersistOutcome:
    final_function_hashes: dict[str, str] = {
        ref.function_name: ref.version_hash for ref in bound_function_refs
    }
    function_ref_node_types: dict[str, str] = {
        ref.function_name: ref.node_type for ref in bound_function_refs
    }
    function_entry: Any
    for function_entry in plan_output.function_entries:
        function_version: FunctionVersionRecord = build_function_version_record(function_entry)
        final_function_hashes[function_entry.name] = function_version.version_hash
        function_ref_node_types[function_entry.name] = str(function_entry.key.resource_type)
        existing_function_version: FunctionVersionRecord | None = (
            runtime.backend.get_function_version(
                state_connection,
                schema=runtime.config.schema,
                function_name=function_version.function_name,
                version_hash=function_version.version_hash,
            )
        )
        if existing_function_version is None:
            runtime.backend.upsert_function_version(
                state_connection,
                schema=runtime.config.schema,
                record=function_version,
            )
    return _FunctionPersistOutcome(
        final_function_hashes=final_function_hashes,
        function_ref_node_types=function_ref_node_types,
    )


def _persist_seed_versions(
    *,
    runtime: _VirtualBuildRuntime,
    state_connection: Any,
    plan_output: PlanOutput,
    reads: _VirtualBuildStateReads,
    seed_results: tuple[SeedExecutionResult, ...],
) -> _SeedPersistOutcome:
    semantics: VirtualPlanSemantics = reads.semantics
    final_seed_hashes: dict[str, str] = {
        ref.seed_name: ref.version_hash for ref in reads.bound_seed_refs
    }
    final_seed_physical_relations: dict[str, PhysicalRelationRecord] = dict(
        reads.available_seed_physical_relations
    )
    for seed_name, relation in reads.available_seed_physical_relations.items():
        final_seed_hashes[seed_name] = relation.version_hash
    successful_seed_names: frozenset[str] = frozenset(
        seed_result.seed_name
        for seed_result in seed_results
        if seed_result.status == ExecutionStatus.SUCCESS
    )
    for seed_name in successful_seed_names:
        version_hash: str | None = semantics.expected_seed_version_hashes.get(seed_name)
        if version_hash is None:
            continue
        target: CompiledRelationLocation | None = plan_output.seed_locations.get(seed_name)
        metadata_json: str = semantics.seed_identity_metadata_jsons.get(seed_name, "{}")
        existing_seed_version: SeedVersionRecord | None = runtime.backend.get_seed_version(
            state_connection,
            schema=runtime.config.schema,
            seed_name=seed_name,
            version_hash=version_hash,
        )
        if existing_seed_version is None:
            runtime.backend.upsert_seed_version(
                state_connection,
                schema=runtime.config.schema,
                record=SeedVersionRecord(
                    seed_name=seed_name,
                    version_hash=version_hash,
                    identity_metadata_hash=hashlib.sha256(
                        metadata_json.encode("utf-8")
                    ).hexdigest(),
                    identity_metadata_json_b64=encode_state_text(metadata_json),
                    status=ModelVersionStatus.READY,
                ),
            )
        if target is not None:
            existing_seed_physical_relation: PhysicalRelationRecord | None = (
                runtime.backend.get_physical_relation_for_artifact(
                    state_connection,
                    schema=runtime.config.schema,
                    artifact_type=PhysicalArtifactType.SEED,
                    artifact_name=seed_name,
                    version_hash=version_hash,
                )
            )
            if existing_seed_physical_relation is None:
                seed_physical_relation: PhysicalRelationRecord = PhysicalRelationRecord(
                    artifact_type=PhysicalArtifactType.SEED,
                    artifact_name=seed_name,
                    version_hash=version_hash,
                    database_name=target.database,
                    schema_name=target.schema or "",
                    relation_name=target.name,
                    relation_type="table",
                )
                runtime.backend.upsert_physical_relation(
                    state_connection,
                    schema=runtime.config.schema,
                    record=seed_physical_relation,
                )
                final_seed_physical_relations[seed_name] = seed_physical_relation
            else:
                final_seed_physical_relations[seed_name] = existing_seed_physical_relation
        final_seed_hashes[seed_name] = version_hash
    for seed_name, version_hash in final_seed_hashes.items():
        if seed_name in final_seed_physical_relations:
            continue
        seed_physical_relation = runtime.backend.get_physical_relation_for_artifact(
            state_connection,
            schema=runtime.config.schema,
            artifact_type=PhysicalArtifactType.SEED,
            artifact_name=seed_name,
            version_hash=version_hash,
        )
        if seed_physical_relation is not None:
            final_seed_physical_relations[seed_name] = seed_physical_relation
    return _SeedPersistOutcome(
        final_seed_hashes=final_seed_hashes,
        final_seed_physical_relations=final_seed_physical_relations,
    )


def _build_node_ref_groups(
    *,
    refs: tuple[VirtualEnvironmentModelRefRecord, ...],
    seed_refs: tuple[VirtualEnvironmentSeedRefRecord, ...],
    function_refs: tuple[VirtualEnvironmentFunctionRefRecord, ...],
) -> dict[str, tuple[VirtualEnvironmentNodeRefRecord, ...]]:
    return {
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
        "udf": tuple(
            VirtualEnvironmentNodeRefRecord(
                virtual_environment_name=ref.virtual_environment_name,
                node_type=ref.node_type,
                node_name=ref.function_name,
                version_hash=ref.version_hash,
            )
            for ref in function_refs
            if ref.node_type == "udf"
        ),
        "table_fn": tuple(
            VirtualEnvironmentNodeRefRecord(
                virtual_environment_name=ref.virtual_environment_name,
                node_type=ref.node_type,
                node_name=ref.function_name,
                version_hash=ref.version_hash,
            )
            for ref in function_refs
            if ref.node_type == "table_fn"
        ),
    }


def _build_virtual_model_changes(
    *,
    project: CompiledProject,
    scope: PlannerScope,
    semantics: VirtualPlanSemantics,
    bound_physical_relations: dict[str, PhysicalRelationRecord],
    full_refresh: bool,
) -> dict[str, ChangeDetectionResult]:
    changes: dict[str, ChangeDetectionResult] = {}
    model: CompiledModel
    for model in project.models:
        if model.key not in scope.selected_keys:
            continue
        changes[model.name] = _build_virtual_model_change(
            model=model,
            semantics=semantics,
            bound_physical_relations=bound_physical_relations,
            full_refresh=full_refresh,
        )
    return changes


def _build_virtual_planner_select(
    *,
    graph: ProjectGraph,
    selected_model_names: tuple[str, ...],
    selected_seed_names: tuple[str, ...] = (),
) -> tuple[str, ...]:
    selected_model_keys: frozenset[CompiledObjectKey] = frozenset(
        key
        for model_name in selected_model_names
        if (key := graph.all_keys.get(model_name)) is not None
    )
    selected_seed_keys: frozenset[CompiledObjectKey] = frozenset(
        key
        for seed_name in selected_seed_names
        if (key := graph.all_keys.get(seed_name)) is not None
    )
    expanded_keys: frozenset[CompiledObjectKey] = expand_build_resource_selection(
        selected_keys=selected_model_keys | selected_seed_keys,
        upstream=graph.upstream_deps,
        downstream=graph.downstream_deps,
        include_upstream_functions=True,
        include_upstream_seeds=False,
        include_downstream_functions=True,
    )
    return tuple(sorted(key.name for key in expanded_keys))


def _resolve_virtual_seed_selection(
    *,
    graph: ProjectGraph,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
) -> tuple[str, ...]:
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
        sorted(key.name for key in selected_keys if key.resource_type == CompiledResourceType.SEED)
    )


def _build_virtual_model_change(
    *,
    model: CompiledModel,
    semantics: VirtualPlanSemantics,
    bound_physical_relations: dict[str, PhysicalRelationRecord],
    full_refresh: bool,
) -> ChangeDetectionResult:
    metadata_json: str = semantics.expected_metadata_jsons.get(model.name, "{}")
    previous_metadata_json: str | None = semantics.bound_metadata_jsons.get(model.name)
    if full_refresh:
        return ChangeDetectionResult(
            model_name=model.name,
            change_kind=ChangeKind.NO_CHANGE,
            fingerprint_metadata_json=metadata_json,
            previous_metadata_json=previous_metadata_json,
            backfill=BackfillResult(action=BackfillAction.FULL),
        )
    if model.name not in bound_physical_relations:
        return ChangeDetectionResult(
            model_name=model.name,
            change_kind=ChangeKind.FIRST_RUN,
            fingerprint_metadata_json=metadata_json,
            previous_metadata_json=previous_metadata_json,
            backfill=BackfillResult(action=BackfillAction.FULL),
        )
    root_reason: PlanReason | None = semantics.stale_root_reasons.get(model.name)
    if root_reason == PlanReason.CONFIG_CHANGED:
        return ChangeDetectionResult(
            model_name=model.name,
            change_kind=ChangeKind.CONFIG_CHANGED,
            config_changed=True,
            fingerprint_metadata_json=metadata_json,
            previous_metadata_json=previous_metadata_json,
        )
    if root_reason in (PlanReason.QUERY_CHANGED, PlanReason.FUNCTION_CHANGED):
        return ChangeDetectionResult(
            model_name=model.name,
            change_kind=ChangeKind.QUERY_CHANGED,
            query_changed=True,
            fingerprint_metadata_json=metadata_json,
            previous_metadata_json=previous_metadata_json,
            backfill=_virtual_root_backfill(model),
        )
    return ChangeDetectionResult(
        model_name=model.name,
        change_kind=ChangeKind.NO_CHANGE,
        fingerprint_metadata_json=metadata_json,
        previous_metadata_json=previous_metadata_json,
    )


def _virtual_root_backfill(model: CompiledModel) -> BackfillResult:
    raw_policy: object | None = model.config.values.get("replay_on_change")
    if raw_policy == BackfillAction.FULL:
        return BackfillResult(action=BackfillAction.FULL)
    if isinstance(raw_policy, str) and raw_policy.startswith("bounded-"):
        duration: str = raw_policy.removeprefix("bounded-").strip()
        if duration:
            return BackfillResult(action=BackfillAction.BOUNDED, duration=duration)
    return BackfillResult(action=BackfillAction.FORWARD_ONLY)


def _create_logical_vde_views(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    target_vde_name: str,
    unsuffixed_virtual_environment_name: str | None,
    plan_output: PlanOutput,
    final_version_hashes: dict[str, str],
    final_seed_physical_relations: dict[str, PhysicalRelationRecord],
) -> None:
    physical_targets: dict[str, CompiledRelationLocation] = {
        model.name: plan_output.model_locations.get(model.name, model.destination)
        for model in project.models
    }
    connection: Any = adapter.connect(connection_config)
    recorder: StatementRecorder = StatementRecorder()
    try:
        model: CompiledModel
        for model in project.models:
            if model.name not in final_version_hashes:
                continue
            physical_target: CompiledRelationLocation | None = physical_targets.get(model.name)
            if physical_target is None:
                continue
            virtual_target: CompiledRelationLocation = build_virtual_destination(
                adapter=adapter,
                target=model.destination,
                virtual_environment_name=target_vde_name,
                unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
            )
            adapter.ensure_schema(
                connection,
                database=virtual_target.database,
                schema=virtual_target.schema,
                statement_recorder=recorder,
            )
            adapter.create_view_as(
                connection,
                destination=resolve_relation_location_qualified_name(
                    adapter=adapter, location=virtual_target
                ),
                sql=(
                    "SELECT * FROM "
                    + resolve_relation_location_qualified_name(
                        adapter=adapter, location=physical_target
                    )
                ),
                statement_recorder=recorder,
            )
        for seed in project.seeds:
            relation: PhysicalRelationRecord | None = final_seed_physical_relations.get(seed.name)
            if relation is None:
                continue
            physical_target: CompiledRelationLocation = build_destination_from_physical_relation(
                adapter=adapter,
                relation=relation,
                fallback_target=seed.destination,
            )
            virtual_target = build_virtual_destination(
                adapter=adapter,
                target=seed.destination,
                virtual_environment_name=target_vde_name,
                unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
            )
            adapter.ensure_schema(
                connection,
                database=virtual_target.database,
                schema=virtual_target.schema,
                statement_recorder=recorder,
            )
            adapter.create_view_as(
                connection,
                destination=resolve_relation_location_qualified_name(
                    adapter=adapter, location=virtual_target
                ),
                sql=(
                    "SELECT * FROM "
                    + resolve_relation_location_qualified_name(
                        adapter=adapter, location=physical_target
                    )
                ),
                statement_recorder=recorder,
            )
    finally:
        adapter.close(connection)
