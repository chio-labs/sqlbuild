"""Virtual clone public entrypoint."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledRelationLocation,
    CompiledSeed,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.clone import run_clone_pipeline
from sqlbuild.compiler.pipeline.models import ClonePipelineResult, ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.shared.helpers.relation_lookup import build_relation_lookup
from sqlbuild.shared.models import RelationLookup
from sqlbuild.shared.types import ExternalSqlReferenceResolver
from sqlbuild.virtual.executor.helpers.clone import (
    acquire_model_lease,
    attach_origin_database_for_clone,
    build_clone_graph_from_project,
    build_workspace_model_versions,
    build_workspace_seed_versions,
    hydrate_relation,
    origin_lookup_location,
    register_hydrated_relation,
    register_hydrated_seed_relation,
    release_model_lease,
)
from sqlbuild.virtual.executor.helpers.rewrite import (
    build_physical_destination,
    build_physical_seed_destination,
)
from sqlbuild.virtual.executor.models import VirtualCloneItemResult, VirtualCloneResult
from sqlbuild.virtual.planner.main.semantics import build_virtual_plan_semantics
from sqlbuild.virtual.planner.models import VirtualPlanSemantics
from sqlbuild.virtual.state.main.runtime import build_state_runtime
from sqlbuild.virtual.state.models import (
    ModelVersionRecord,
    SeedVersionRecord,
    StateLockLease,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentSeedRefRecord,
)
from sqlbuild.virtual.state.types import PhysicalArtifactType


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
    seed_names: tuple[str, ...] = tuple(
        entry.name for entry in clone_pipeline.destination_seed_entries
    )
    destination_models_by_name: dict[str, CompiledModel] = {
        model.name: model for model in clone_pipeline.destination_project.models
    }
    origin_models_by_name: dict[str, CompiledModel] = {
        model.name: model for model in clone_pipeline.origin_project.models
    }
    destination_seeds_by_name: dict[str, CompiledSeed] = {
        seed.name: seed for seed in clone_pipeline.destination_project.seeds
    }
    origin_seeds_by_name: dict[str, CompiledSeed] = {
        seed.name: seed for seed in clone_pipeline.origin_project.seeds
    }

    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs, project_dir=project_dir
    )
    state_connection: Any = backend.connect(config.connection)
    mode: str
    seed_versions: dict[str, SeedVersionRecord]
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
            seed_hashes: dict[str, str] = semantics.expected_seed_version_hashes
            seed_versions = build_workspace_seed_versions(
                project=clone_pipeline.destination_project,
                seed_entries=clone_pipeline.destination_seed_entries,
                seed_names=seed_names,
                version_hashes=seed_hashes,
                metadata_jsons=semantics.seed_identity_metadata_jsons,
            )
            mode = "workspace fingerprints"
        else:
            refs: tuple[VirtualEnvironmentModelRefRecord, ...] = (
                backend.get_virtual_environment_model_refs(
                    state_connection,
                    schema=config.schema,
                    virtual_environment_name=virtual_environment_name,
                )
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
            seed_refs: tuple[VirtualEnvironmentSeedRefRecord, ...] = (
                backend.get_virtual_environment_seed_refs(
                    state_connection,
                    schema=config.schema,
                    virtual_environment_name=virtual_environment_name,
                )
            )
            seed_hashes = {ref.seed_name: ref.version_hash for ref in seed_refs}
            missing_seed_refs: tuple[str, ...] = tuple(
                name for name in seed_names if name not in seed_hashes
            )
            if missing_seed_refs:
                raise PlannerInputError(
                    "destination virtual environment is missing selected seed refs: "
                    + ", ".join(missing_seed_refs),
                    code="S020",
                )
            seed_versions = {}
            for name in seed_names:
                seed_version_hash: str = seed_hashes[name]
                seed_record: SeedVersionRecord | None = backend.get_seed_version(
                    state_connection,
                    schema=config.schema,
                    seed_name=name,
                    version_hash=seed_version_hash,
                )
                if seed_record is None:
                    raise PlannerInputError(
                        "destination virtual environment has a ref without seed version state: "
                        + name,
                        code="S021",
                    )
                seed_versions[name] = seed_record
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
    model_origin_lookup_locations: dict[str, CompiledRelationLocation] = {
        model_name: origin_lookup_location(
            adapter=adapter,
            location=build_physical_destination(
                adapter=adapter,
                target=origin_models_by_name[model_name].destination,
                model_name=model_name,
                version_hash=version_hashes[model_name],
            ),
            origin_database_alias=origin_database_alias,
        )
        for model_name in model_names
    }
    seed_origin_lookup_locations: dict[str, CompiledRelationLocation] = {
        seed_name: origin_lookup_location(
            adapter=adapter,
            location=build_physical_seed_destination(
                adapter=adapter,
                target=origin_seeds_by_name[seed_name].destination,
                seed_name=seed_name,
                version_hash=seed_versions[seed_name].version_hash,
            ),
            origin_database_alias=origin_database_alias,
        )
        for seed_name in seed_names
    }
    origin_lookup: RelationLookup = build_relation_lookup(
        adapter=adapter,
        connection=origin_connection,
        locations=tuple(
            (location.database, location.schema, location.name)
            for location in (
                *model_origin_lookup_locations.values(),
                *seed_origin_lookup_locations.values(),
            )
        ),
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
            lookup_location: CompiledRelationLocation = model_origin_lookup_locations[model_name]
            destination_location: CompiledRelationLocation = build_physical_destination(
                adapter=adapter,
                target=destination_model.destination,
                model_name=model_name,
                version_hash=version_hash,
            )
            if not origin_lookup.exists(
                database=lookup_location.database,
                schema=lookup_location.schema,
                name=lookup_location.name,
            ):
                results.append(
                    VirtualCloneItemResult(
                        PhysicalArtifactType.MODEL, model_name, version_hash, "missing"
                    )
                )
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
                        VirtualCloneItemResult(
                            PhysicalArtifactType.MODEL,
                            model_name,
                            version_hash,
                            "skipped_locked",
                        )
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
                results.append(
                    VirtualCloneItemResult(
                        PhysicalArtifactType.MODEL, model_name, version_hash, action
                    )
                )
            finally:
                release_model_lease(
                    backend=backend,
                    config_schema=config.schema,
                    config_connection=config.connection,
                    lease=lease,
                )
        for seed_name in seed_names:
            destination_seed: CompiledSeed = destination_seeds_by_name[seed_name]
            origin_seed: CompiledSeed = origin_seeds_by_name[seed_name]
            seed_version: SeedVersionRecord = seed_versions[seed_name]
            seed_version_hash: str = seed_version.version_hash
            origin_location = build_physical_seed_destination(
                adapter=adapter,
                target=origin_seed.destination,
                seed_name=seed_name,
                version_hash=seed_version_hash,
            )
            lookup_location = seed_origin_lookup_locations[seed_name]
            destination_location = build_physical_seed_destination(
                adapter=adapter,
                target=destination_seed.destination,
                seed_name=seed_name,
                version_hash=seed_version_hash,
            )
            if not origin_lookup.exists(
                database=lookup_location.database,
                schema=lookup_location.schema,
                name=lookup_location.name,
            ):
                results.append(
                    VirtualCloneItemResult(
                        PhysicalArtifactType.SEED,
                        seed_name,
                        seed_version_hash,
                        "missing",
                    )
                )
                continue
            action = hydrate_relation(
                adapter=adapter,
                destination_connection=destination_connection,
                origin_location=origin_location,
                destination_location=destination_location,
                origin_database_alias=origin_database_alias,
            )
            register_hydrated_seed_relation(
                backend=backend,
                config_schema=config.schema,
                config_connection=config.connection,
                seed_version=seed_version,
                destination=destination_location,
            )
            results.append(
                VirtualCloneItemResult(
                    PhysicalArtifactType.SEED,
                    seed_name,
                    seed_version_hash,
                    action,
                )
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
