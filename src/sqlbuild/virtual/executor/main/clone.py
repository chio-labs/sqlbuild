"""Virtual clone public entrypoint."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import CompiledModel, CompiledRelationLocation
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.clone import run_clone_pipeline
from sqlbuild.compiler.pipeline.models import ClonePipelineResult, ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.shared.types import ExternalSqlReferenceResolver
from sqlbuild.virtual.executor.helpers.clone import (
    acquire_model_lease,
    attach_origin_database_for_clone,
    build_clone_graph_from_project,
    build_workspace_model_versions,
    hydrate_relation,
    register_hydrated_relation,
    release_model_lease,
    replace_location_database,
)
from sqlbuild.virtual.executor.helpers.rewrite import build_physical_destination
from sqlbuild.virtual.executor.models import VirtualCloneItemResult, VirtualCloneResult
from sqlbuild.virtual.planner.main.semantics import build_virtual_plan_semantics
from sqlbuild.virtual.planner.models import VirtualPlanSemantics
from sqlbuild.virtual.state.main.runtime import build_state_runtime
from sqlbuild.virtual.state.models import (
    ModelVersionRecord,
    StateLockLease,
    VirtualEnvironmentRefRecord,
)


def run_virtual_clone(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    origin_target_name: str,
    destination_target_name: str,
    origin_connection_config: dict[str, object],
    destination_connection_config: dict[str, object],
    virtual_environment_name: str | None = None,
    skip_locked: bool = False,
    no_sql_validation: bool = False,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    cli_vars: dict[str, object] | None = None,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
) -> VirtualCloneResult:
    """Hydrate target physical versions from matching source warehouse artifacts."""

    pipeline_destination_connection: Any = adapter.connect(destination_connection_config)
    try:
        clone_pipeline: ClonePipelineResult = run_clone_pipeline(
            discovered_inputs=discovered_inputs,
            adapter=adapter,
            origin_target_name=origin_target_name,
            destination_target_name=destination_target_name,
            no_sql_validation=no_sql_validation,
            select=select,
            exclude=exclude,
            cli_vars=cli_vars,
            destination_connection=pipeline_destination_connection,
            external_sql_reference_resolver=external_sql_reference_resolver,
        )
    finally:
        adapter.close(pipeline_destination_connection)
    destination_graph: ProjectGraph = build_clone_graph_from_project(
        project=clone_pipeline.destination_project
    )
    model_names: tuple[str, ...] = tuple(
        entry.name for entry in clone_pipeline.destination_model_entries
    )
    destination_models_by_name: dict[str, CompiledModel] = {
        model.name: model for model in clone_pipeline.destination_project.models
    }
    origin_models_by_name: dict[str, CompiledModel] = {
        model.name: model for model in clone_pipeline.origin_project.models
    }

    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs, project_dir=project_dir
    )
    state_connection: Any = backend.connect(config.connection)
    mode: str
    try:
        if virtual_environment_name is None:
            semantics: VirtualPlanSemantics = build_virtual_plan_semantics(
                graph=destination_graph,
                bound_refs=(),
                bound_model_versions={},
            )
            version_hashes: dict[str, str] = semantics.expected_version_hashes
            model_versions: dict[str, ModelVersionRecord] = build_workspace_model_versions(
                project=clone_pipeline.destination_project,
                model_entries=clone_pipeline.destination_model_entries,
                model_names=model_names,
                version_hashes=version_hashes,
                local_hashes=semantics.expected_local_hashes,
                metadata_jsons=semantics.expected_metadata_jsons,
            )
            mode = "workspace fingerprints"
        else:
            refs: tuple[VirtualEnvironmentRefRecord, ...] = backend.get_virtual_environment_refs(
                state_connection,
                schema=config.schema,
                virtual_environment_name=virtual_environment_name,
            )
            if not refs:
                raise PlannerInputError(
                    f"unknown destination virtual environment '{virtual_environment_name}'",
                    code="S019",
                )
            ref_hashes: dict[str, str] = {ref.model_name: ref.version_hash for ref in refs}
            missing_refs: tuple[str, ...] = tuple(
                name for name in model_names if name not in ref_hashes
            )
            if missing_refs:
                raise PlannerInputError(
                    "destination virtual environment is missing selected refs: "
                    + ", ".join(missing_refs),
                    code="S020",
                )
            version_hashes = ref_hashes
            model_versions = {}
            for name in model_names:
                version_hash: str = version_hashes[name]
                record: ModelVersionRecord | None = backend.get_model_version(
                    state_connection,
                    schema=config.schema,
                    model_name=name,
                    version_hash=version_hash,
                )
                if record is None:
                    raise PlannerInputError(
                        "destination virtual environment has a ref without model version state: "
                        + name,
                        code="S021",
                    )
                model_versions[name] = record
            mode = "destination VDE refs"
    finally:
        backend.close(state_connection)

    destination_connection: Any = adapter.connect(destination_connection_config)
    origin_database_alias: str | None = attach_origin_database_for_clone(
        adapter=adapter,
        destination_connection=destination_connection,
        origin_connection_config=origin_connection_config,
        destination_connection_config=destination_connection_config,
    )
    origin_connection: Any = (
        destination_connection
        if origin_database_alias is not None
        else adapter.connect(origin_connection_config)
    )
    results: list[VirtualCloneItemResult] = []
    try:
        for model_name in model_names:
            destination_model: CompiledModel = destination_models_by_name[model_name]
            origin_model: CompiledModel = origin_models_by_name[model_name]
            version_hash: str = version_hashes[model_name]
            origin_location: CompiledRelationLocation = build_physical_destination(
                adapter=adapter,
                target=origin_model.destination,
                model_name=model_name,
                version_hash=version_hash,
            )
            origin_lookup_location: CompiledRelationLocation = (
                replace_location_database(
                    adapter=adapter,
                    location=origin_location,
                    database=origin_database_alias,
                )
                if origin_database_alias is not None
                else origin_location
            )
            destination_location: CompiledRelationLocation = build_physical_destination(
                adapter=adapter,
                target=destination_model.destination,
                model_name=model_name,
                version_hash=version_hash,
            )
            if not adapter.relation_exists(
                origin_connection,
                database=origin_lookup_location.database,
                schema=origin_lookup_location.schema,
                name=origin_lookup_location.name,
            ):
                results.append(VirtualCloneItemResult(model_name, version_hash, "missing"))
                continue
            lease: StateLockLease | None = acquire_model_lease(
                backend=backend,
                config_schema=config.schema,
                config_connection=config.connection,
                model_name=model_name,
                version_hash=version_hash,
            )
            if lease is None:
                if skip_locked:
                    results.append(
                        VirtualCloneItemResult(model_name, version_hash, "skipped_locked")
                    )
                    continue
                raise PlannerInputError(
                    f"model version '{model_name}:{version_hash}' is locked",
                    code="S022",
                    help="Re-run with --skip-locked to hydrate other model versions.",
                )
            try:
                action: str = hydrate_relation(
                    adapter=adapter,
                    destination_connection=destination_connection,
                    origin_location=origin_location,
                    destination_location=destination_location,
                    origin_database_alias=origin_database_alias,
                )
                register_hydrated_relation(
                    backend=backend,
                    config_schema=config.schema,
                    config_connection=config.connection,
                    model_version=model_versions[model_name],
                    model=destination_model,
                    destination=destination_location,
                )
                results.append(VirtualCloneItemResult(model_name, version_hash, action))
            finally:
                release_model_lease(
                    backend=backend,
                    config_schema=config.schema,
                    config_connection=config.connection,
                    lease=lease,
                )
    finally:
        if origin_connection is not destination_connection:
            adapter.close(origin_connection)
        adapter.close(destination_connection)

    return VirtualCloneResult(
        mode=mode,
        origin_environment=origin_target_name,
        destination_environment=destination_target_name,
        destination_virtual_environment=virtual_environment_name,
        item_results=tuple(results),
    )
