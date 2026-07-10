"""Virtual clone helper operations."""

from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.main.relation_lookup import build_relation_lookup
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.adapter.shared.types import BuiltinAdapter
from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledProject,
    CompiledRelationLocation,
    CompiledSeed,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.clone import run_clone_pipeline
from sqlbuild.compiler.pipeline.main.project_graph import (
    build_project_graph_from_compiled_project,
)
from sqlbuild.compiler.pipeline.models import ClonePipelineResult, ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import ModelPlanEntry, SeedPlanEntry
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.shared.helpers.identity.naming import (
    resolve_qualified_name_parts,
    resolve_relation_location_qualified_name,
)
from sqlbuild.shared.models import RelationLookup
from sqlbuild.shared.types import ExternalSqlReferenceResolver
from sqlbuild.virtual.executor.helpers.rewrite import (
    build_physical_destination,
    build_physical_seed_destination,
    relation_type_for_model,
)
from sqlbuild.virtual.executor.models import (
    CloneOriginLookup,
    CloneProjectContext,
    CloneVersions,
    VirtualCloneItemResult,
)
from sqlbuild.virtual.planner.main.semantics import build_virtual_plan_semantics
from sqlbuild.virtual.planner.models import VirtualPlanSemantics
from sqlbuild.virtual.shared.helpers.encoding import encode_state_text
from sqlbuild.virtual.state.main.locks.model_version_lock import acquire_model_version_lease
from sqlbuild.virtual.state.main.locks.release_lock import release_state_lease
from sqlbuild.virtual.state.models import (
    ModelVersionRecord,
    PhysicalRelationRecord,
    SeedVersionRecord,
    StateLockLease,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentSeedRefRecord,
)
from sqlbuild.virtual.state.types import ModelVersionStatus, PhysicalArtifactType


def build_clone_graph_from_project(project: CompiledProject) -> ProjectGraph:
    return build_project_graph_from_compiled_project(project=project)


def build_workspace_model_versions(
    *,
    project: CompiledProject,
    model_entries: tuple[ModelPlanEntry, ...],
    model_names: tuple[str, ...],
    version_hashes: dict[str, str],
    local_hashes: dict[str, str],
    metadata_jsons: dict[str, str],
) -> dict[str, ModelVersionRecord]:
    models_by_name: dict[str, CompiledModel] = {model.name: model for model in project.models}
    model_entries_by_name: dict[str, ModelPlanEntry] = {
        entry.name: entry for entry in model_entries
    }
    records: dict[str, ModelVersionRecord] = {}
    for name in model_names:
        model: CompiledModel = models_by_name[name]
        entry: ModelPlanEntry | None = model_entries_by_name.get(name)
        metadata_json: str = metadata_jsons.get(name, "{}")
        records[name] = ModelVersionRecord(
            model_name=name,
            version_hash=version_hashes[name],
            definition_identity_hash=local_hashes.get(name, version_hashes[name]),
            identity_metadata_hash=hashlib.sha256(metadata_json.encode("utf-8")).hexdigest(),
            status=ModelVersionStatus.READY,
            definition_text_b64=encode_state_text(model.query_sql),
            identity_metadata_json_b64=encode_state_text(metadata_json),
            compiled_sql_b64=encode_state_text(entry.resolved_sql) if entry is not None else None,
        )
    return records


def build_workspace_seed_versions(
    *,
    project: CompiledProject,
    seed_entries: tuple[SeedPlanEntry, ...],
    seed_names: tuple[str, ...],
    version_hashes: dict[str, str],
    metadata_jsons: dict[str, str],
) -> dict[str, SeedVersionRecord]:
    seeds_by_name: dict[str, CompiledSeed] = {seed.name: seed for seed in project.seeds}
    seed_entries_by_name: dict[str, SeedPlanEntry] = {entry.name: entry for entry in seed_entries}
    records: dict[str, SeedVersionRecord] = {}
    for name in seed_names:
        if name not in seeds_by_name or name not in seed_entries_by_name:
            continue
        metadata_json: str = metadata_jsons.get(name, "{}")
        records[name] = SeedVersionRecord(
            seed_name=name,
            version_hash=version_hashes[name],
            identity_metadata_hash=hashlib.sha256(metadata_json.encode("utf-8")).hexdigest(),
            identity_metadata_json_b64=encode_state_text(metadata_json),
            status=ModelVersionStatus.READY,
        )
    return records


def hydrate_relation(
    *,
    adapter: BaseAdapter,
    destination_connection: Any,
    origin_location: CompiledRelationLocation,
    destination_location: CompiledRelationLocation,
    origin_database_alias: str | None,
) -> str:
    if adapter.relation_exists(
        destination_connection,
        database=destination_location.database,
        schema=destination_location.schema,
        name=destination_location.name,
    ):
        return "reused"
    adapter.ensure_schema(
        destination_connection,
        database=destination_location.database,
        schema=destination_location.schema or "",
        statement_recorder=StatementRecorder(),
    )
    clone_origin_location: CompiledRelationLocation = (
        replace_location_database(
            adapter=adapter, location=origin_location, database=origin_database_alias
        )
        if origin_database_alias is not None
        else origin_location
    )
    adapter.durable_clone(
        destination_connection,
        origin=resolve_relation_location_qualified_name(
            adapter=adapter, location=clone_origin_location
        ),
        destination=resolve_relation_location_qualified_name(
            adapter=adapter, location=destination_location
        ),
        origin_is_transient=_location_is_transient(
            adapter=adapter, connection=destination_connection, location=clone_origin_location
        ),
        statement_recorder=StatementRecorder(),
    )
    return "hydrated"


def _location_is_transient(
    *, adapter: BaseAdapter, connection: Any, location: CompiledRelationLocation
) -> bool:
    """Return whether the origin warehouse relation is transient, defaulting to False."""

    if location.schema is None:
        return False
    relations: tuple[Any, ...] = adapter.list_relations(
        connection,
        database=location.database,
        schemas=(location.schema,),
        names=(location.name,),
    )
    target_name: str = location.name.lower()
    for relation in relations:
        if relation.name == target_name:
            return bool(relation.is_transient)
    return False


def acquire_model_lease(
    *,
    backend: Any,
    config_schema: str,
    config_connection: dict[str, object],
    model_name: str,
    version_hash: str,
) -> StateLockLease | None:
    connection: Any = backend.connect(config_connection)
    try:
        return acquire_model_version_lease(
            backend,
            connection=connection,
            schema=config_schema,
            model_name=model_name,
            version_hash=version_hash,
            owner_id=f"clone:{uuid.uuid4()}",
            ttl=timedelta(minutes=10),
        )
    finally:
        backend.close(connection)


def release_model_lease(
    *, backend: Any, config_schema: str, config_connection: dict[str, object], lease: StateLockLease
) -> None:
    connection: Any = backend.connect(config_connection)
    try:
        release_state_lease(backend, connection=connection, schema=config_schema, lease=lease)
    finally:
        backend.close(connection)


def register_hydrated_relation(
    *,
    backend: Any,
    config_schema: str,
    config_connection: dict[str, object],
    model_version: ModelVersionRecord,
    model: CompiledModel,
    destination: CompiledRelationLocation,
) -> None:
    connection: Any = backend.connect(config_connection)
    try:
        if (
            backend.get_model_version(
                connection,
                schema=config_schema,
                model_name=model_version.model_name,
                version_hash=model_version.version_hash,
            )
            is None
        ):
            backend.upsert_model_version(connection, schema=config_schema, record=model_version)
        if (
            backend.get_physical_relation(
                connection,
                schema=config_schema,
                model_name=model.name,
                version_hash=model_version.version_hash,
            )
            is None
        ):
            backend.upsert_physical_relation(
                connection,
                schema=config_schema,
                record=PhysicalRelationRecord(
                    artifact_type=PhysicalArtifactType.MODEL,
                    artifact_name=model.name,
                    version_hash=model_version.version_hash,
                    database_name=destination.database,
                    schema_name=destination.schema or "",
                    relation_name=destination.name,
                    relation_type=relation_type_for_model(
                        MaterializationType(
                            model.config.values.get("materialized", MaterializationType.TABLE)
                        )
                    ),
                ),
            )
    finally:
        backend.close(connection)


def register_hydrated_seed_relation(
    *,
    backend: Any,
    config_schema: str,
    config_connection: dict[str, object],
    seed_version: SeedVersionRecord,
    destination: CompiledRelationLocation,
) -> None:
    connection: Any = backend.connect(config_connection)
    try:
        if (
            backend.get_seed_version(
                connection,
                schema=config_schema,
                seed_name=seed_version.seed_name,
                version_hash=seed_version.version_hash,
            )
            is None
        ):
            backend.upsert_seed_version(connection, schema=config_schema, record=seed_version)
        if (
            backend.get_physical_relation_for_artifact(
                connection,
                schema=config_schema,
                artifact_type=PhysicalArtifactType.SEED,
                artifact_name=seed_version.seed_name,
                version_hash=seed_version.version_hash,
            )
            is None
        ):
            backend.upsert_physical_relation(
                connection,
                schema=config_schema,
                record=PhysicalRelationRecord(
                    artifact_type=PhysicalArtifactType.SEED,
                    artifact_name=seed_version.seed_name,
                    version_hash=seed_version.version_hash,
                    database_name=destination.database,
                    schema_name=destination.schema or "",
                    relation_name=destination.name,
                    relation_type="table",
                ),
            )
    finally:
        backend.close(connection)


def attach_origin_database_for_clone(
    *,
    adapter: BaseAdapter,
    destination_connection: Any,
    origin_connection_config: dict[str, object],
    destination_connection_config: dict[str, object],
) -> str | None:
    if adapter.adapter_name != BuiltinAdapter.DUCKDB:
        return None
    origin_database: object | None = origin_connection_config.get("database")
    destination_database: object | None = destination_connection_config.get("database")
    if origin_database is None or origin_database in {destination_database, ":memory:"}:
        return None
    alias: str = "__sqb_clone_origin"
    adapter.execute(
        destination_connection,
        sql=f"ATTACH '{str(origin_database)}' AS {alias} (READ_ONLY)",
    )
    return alias


def replace_location_database(
    *, adapter: BaseAdapter, location: CompiledRelationLocation, database: str
) -> CompiledRelationLocation:
    return CompiledRelationLocation(
        database=database,
        schema=location.schema,
        name=location.name,
        qualified_name=resolve_qualified_name_parts(
            adapter=adapter, database=database, schema=location.schema, name=location.name
        ),
        logical_schema=location.logical_schema,
        logical_database=location.logical_database,
    )


def origin_lookup_location(
    *,
    adapter: BaseAdapter,
    location: CompiledRelationLocation,
    origin_database_alias: str | None,
) -> CompiledRelationLocation:
    """Resolve the origin relation location, applying the attached-database alias when present."""

    if origin_database_alias is None:
        return location
    return replace_location_database(
        adapter=adapter, location=location, database=origin_database_alias
    )


def compile_clone_pipeline(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    origin_target_name: str,
    destination_target_name: str,
    destination_connection_config: dict[str, object],
    no_sql_validation: bool,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    cli_vars: dict[str, object] | None,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None,
) -> ClonePipelineResult:
    """Compile origin and destination projects for one clone run."""

    pipeline_destination_connection: Any = adapter.connect(destination_connection_config)
    try:
        return run_clone_pipeline(
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


def build_clone_project_context(clone_pipeline: ClonePipelineResult) -> CloneProjectContext:
    """Build the destination graph and node lookups from the clone pipeline result."""

    return CloneProjectContext(
        destination_graph=build_clone_graph_from_project(
            project=clone_pipeline.destination_project
        ),
        model_names=tuple(entry.name for entry in clone_pipeline.destination_model_entries),
        seed_names=tuple(entry.name for entry in clone_pipeline.destination_seed_entries),
        destination_models_by_name={
            model.name: model for model in clone_pipeline.destination_project.models
        },
        origin_models_by_name={model.name: model for model in clone_pipeline.origin_project.models},
        destination_seeds_by_name={
            seed.name: seed for seed in clone_pipeline.destination_project.seeds
        },
        origin_seeds_by_name={seed.name: seed for seed in clone_pipeline.origin_project.seeds},
    )


def resolve_clone_versions(
    backend: Any,
    *,
    state_connection: Any,
    schema: str,
    clone_pipeline: ClonePipelineResult,
    context: CloneProjectContext,
    virtual_environment_name: str | None,
) -> CloneVersions:
    """Resolve model and seed version records to hydrate."""

    if virtual_environment_name is None:
        return _resolve_workspace_clone_versions(clone_pipeline=clone_pipeline, context=context)
    return _read_virtual_environment_clone_versions(
        backend,
        state_connection=state_connection,
        schema=schema,
        context=context,
        virtual_environment_name=virtual_environment_name,
    )


def build_clone_origin_lookup(
    *,
    adapter: BaseAdapter,
    origin_connection: Any,
    context: CloneProjectContext,
    versions: CloneVersions,
    origin_database_alias: str | None,
) -> CloneOriginLookup:
    """Build origin lookup locations and the relation existence lookup."""

    model_locations: dict[str, CompiledRelationLocation] = {
        model_name: origin_lookup_location(
            adapter=adapter,
            location=build_physical_destination(
                adapter=adapter,
                target=context.origin_models_by_name[model_name].destination,
                model_name=model_name,
                version_hash=versions.version_hashes[model_name],
            ),
            origin_database_alias=origin_database_alias,
        )
        for model_name in context.model_names
    }
    seed_locations: dict[str, CompiledRelationLocation] = {
        seed_name: origin_lookup_location(
            adapter=adapter,
            location=build_physical_seed_destination(
                adapter=adapter,
                target=context.origin_seeds_by_name[seed_name].destination,
                seed_name=seed_name,
                version_hash=versions.seed_versions[seed_name].version_hash,
            ),
            origin_database_alias=origin_database_alias,
        )
        for seed_name in context.seed_names
    }
    lookup: RelationLookup = build_relation_lookup(
        adapter=adapter,
        connection=origin_connection,
        locations=tuple(
            (location.database, location.schema, location.name)
            for location in (*model_locations.values(), *seed_locations.values())
        ),
    )
    return CloneOriginLookup(
        model_locations=model_locations,
        seed_locations=seed_locations,
        origin_database_alias=origin_database_alias,
        lookup=lookup,
    )


def hydrate_clone_model_relations(
    backend: Any,
    *,
    adapter: BaseAdapter,
    destination_connection: Any,
    config_schema: str,
    config_connection: Any,
    context: CloneProjectContext,
    versions: CloneVersions,
    origin_lookup: CloneOriginLookup,
    skip_locked: bool,
) -> tuple[VirtualCloneItemResult, ...]:
    """Hydrate selected model relations from origin warehouse artifacts."""

    results: list[VirtualCloneItemResult] = []
    for model_name in context.model_names:
        destination_model: CompiledModel = context.destination_models_by_name[model_name]
        origin_model: CompiledModel = context.origin_models_by_name[model_name]
        version_hash: str = versions.version_hashes[model_name]
        origin_location: CompiledRelationLocation = build_physical_destination(
            adapter=adapter,
            target=origin_model.destination,
            model_name=model_name,
            version_hash=version_hash,
        )
        lookup_location: CompiledRelationLocation = origin_lookup.model_locations[model_name]
        destination_location: CompiledRelationLocation = build_physical_destination(
            adapter=adapter,
            target=destination_model.destination,
            model_name=model_name,
            version_hash=version_hash,
        )
        if not origin_lookup.lookup.exists(
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
            config_schema=config_schema,
            config_connection=config_connection,
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
                origin_database_alias=origin_lookup.origin_database_alias,
            )
            register_hydrated_relation(
                backend=backend,
                config_schema=config_schema,
                config_connection=config_connection,
                model_version=versions.model_versions[model_name],
                model=destination_model,
                destination=destination_location,
            )
            results.append(
                VirtualCloneItemResult(PhysicalArtifactType.MODEL, model_name, version_hash, action)
            )
        finally:
            release_model_lease(
                backend=backend,
                config_schema=config_schema,
                config_connection=config_connection,
                lease=lease,
            )
    return tuple(results)


def hydrate_clone_seed_relations(
    backend: Any,
    *,
    adapter: BaseAdapter,
    destination_connection: Any,
    config_schema: str,
    config_connection: Any,
    context: CloneProjectContext,
    versions: CloneVersions,
    origin_lookup: CloneOriginLookup,
) -> tuple[VirtualCloneItemResult, ...]:
    """Hydrate selected seed relations from origin warehouse artifacts."""

    results: list[VirtualCloneItemResult] = []
    for seed_name in context.seed_names:
        destination_seed: CompiledSeed = context.destination_seeds_by_name[seed_name]
        origin_seed: CompiledSeed = context.origin_seeds_by_name[seed_name]
        seed_version: SeedVersionRecord = versions.seed_versions[seed_name]
        seed_version_hash: str = seed_version.version_hash
        origin_location: CompiledRelationLocation = build_physical_seed_destination(
            adapter=adapter,
            target=origin_seed.destination,
            seed_name=seed_name,
            version_hash=seed_version_hash,
        )
        lookup_location: CompiledRelationLocation = origin_lookup.seed_locations[seed_name]
        destination_location: CompiledRelationLocation = build_physical_seed_destination(
            adapter=adapter,
            target=destination_seed.destination,
            seed_name=seed_name,
            version_hash=seed_version_hash,
        )
        if not origin_lookup.lookup.exists(
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
        action: str = hydrate_relation(
            adapter=adapter,
            destination_connection=destination_connection,
            origin_location=origin_location,
            destination_location=destination_location,
            origin_database_alias=origin_lookup.origin_database_alias,
        )
        register_hydrated_seed_relation(
            backend=backend,
            config_schema=config_schema,
            config_connection=config_connection,
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
    return tuple(results)


def _resolve_workspace_clone_versions(
    *,
    clone_pipeline: ClonePipelineResult,
    context: CloneProjectContext,
) -> CloneVersions:
    semantics: VirtualPlanSemantics = build_virtual_plan_semantics(
        graph=context.destination_graph,
        bound_refs=(),
        bound_model_versions={},
    )
    version_hashes: dict[str, str] = semantics.expected_version_hashes
    model_versions: dict[str, ModelVersionRecord] = build_workspace_model_versions(
        project=clone_pipeline.destination_project,
        model_entries=clone_pipeline.destination_model_entries,
        model_names=context.model_names,
        version_hashes=version_hashes,
        local_hashes=semantics.expected_local_hashes,
        metadata_jsons=semantics.expected_metadata_jsons,
    )
    seed_versions: dict[str, SeedVersionRecord] = build_workspace_seed_versions(
        project=clone_pipeline.destination_project,
        seed_entries=clone_pipeline.destination_seed_entries,
        seed_names=context.seed_names,
        version_hashes=semantics.expected_seed_version_hashes,
        metadata_jsons=semantics.seed_identity_metadata_jsons,
    )
    return CloneVersions(
        mode="workspace fingerprints",
        version_hashes=version_hashes,
        model_versions=model_versions,
        seed_versions=seed_versions,
    )


def _read_virtual_environment_clone_versions(
    backend: Any,
    *,
    state_connection: Any,
    schema: str,
    context: CloneProjectContext,
    virtual_environment_name: str,
) -> CloneVersions:
    refs: tuple[VirtualEnvironmentModelRefRecord, ...] = backend.get_virtual_environment_model_refs(
        state_connection,
        schema=schema,
        virtual_environment_name=virtual_environment_name,
    )
    if not refs:
        raise PlannerInputError(
            f"unknown destination virtual environment '{virtual_environment_name}'",
            code="S019",
        )
    ref_hashes: dict[str, str] = {ref.model_name: ref.version_hash for ref in refs}
    missing_refs: tuple[str, ...] = tuple(
        name for name in context.model_names if name not in ref_hashes
    )
    if missing_refs:
        raise PlannerInputError(
            "destination virtual environment is missing selected refs: " + ", ".join(missing_refs),
            code="S020",
        )
    model_versions: dict[str, ModelVersionRecord] = {}
    for name in context.model_names:
        version_hash: str = ref_hashes[name]
        record: ModelVersionRecord | None = backend.get_model_version(
            state_connection,
            schema=schema,
            model_name=name,
            version_hash=version_hash,
        )
        if record is None:
            raise PlannerInputError(
                "destination virtual environment has a ref without model version state: " + name,
                code="S021",
            )
        model_versions[name] = record
    seed_refs: tuple[VirtualEnvironmentSeedRefRecord, ...] = (
        backend.get_virtual_environment_seed_refs(
            state_connection,
            schema=schema,
            virtual_environment_name=virtual_environment_name,
        )
    )
    seed_hashes: dict[str, str] = {ref.seed_name: ref.version_hash for ref in seed_refs}
    missing_seed_refs: tuple[str, ...] = tuple(
        name for name in context.seed_names if name not in seed_hashes
    )
    if missing_seed_refs:
        raise PlannerInputError(
            "destination virtual environment is missing selected seed refs: "
            + ", ".join(missing_seed_refs),
            code="S020",
        )
    seed_versions: dict[str, SeedVersionRecord] = {}
    for name in context.seed_names:
        seed_version_hash: str = seed_hashes[name]
        seed_record: SeedVersionRecord | None = backend.get_seed_version(
            state_connection,
            schema=schema,
            seed_name=name,
            version_hash=seed_version_hash,
        )
        if seed_record is None:
            raise PlannerInputError(
                "destination virtual environment has a ref without seed version state: " + name,
                code="S021",
            )
        seed_versions[name] = seed_record
    return CloneVersions(
        mode="destination VDE refs",
        version_hashes=ref_hashes,
        model_versions=model_versions,
        seed_versions=seed_versions,
    )
