"""Virtual clone helper operations."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from datetime import timedelta
from functools import partial
from pathlib import Path
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.models import RelationLookup
from sqlbuild.adapter.relations.main.relation_lookup import build_relation_lookup
from sqlbuild.adapter.relations.main.resolve_relation_location_qualified_name import (
    resolve_relation_location_qualified_name,
)
from sqlbuild.compiler.compile.models import (
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
from sqlbuild.compiler.pipeline.models import (
    ClonePipelineConnection,
    ClonePipelineResult,
    ProjectGraph,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import ModelPlanEntry, SeedPlanEntry
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle
from sqlbuild.runtime.observability.classes.resource_attempt_lifecycle import (
    ResourceAttemptLifecycle,
)
from sqlbuild.spec.contracts.main.resolve_target_config import resolve_target_config
from sqlbuild.virtual.executor._helpers.rewrite import (
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
from sqlbuild.virtual.planner.main._semantics import build_virtual_plan_semantics
from sqlbuild.virtual.planner.models import VirtualPlanSemantics
from sqlbuild.virtual.state.exceptions import StateBackendConfigError
from sqlbuild.virtual.state.main.encoding._encode_state_text import encode_state_text
from sqlbuild.virtual.state.main.locks._model_version_lock import acquire_model_version_lease
from sqlbuild.virtual.state.main.locks._release_lock import release_state_lease
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
) -> str:
    with OperationLifecycle(operation_kind="clone", operation_name="clone_relation_transfer"):
        adapter.ensure_schema(
            connection=destination_connection,
            database=destination_location.database,
            schema=destination_location.schema or "",
            statement_recorder=StatementRecorder(),
        )
        adapter.durable_clone(
            connection=destination_connection,
            origin=resolve_relation_location_qualified_name(
                adapter=adapter, location=origin_location
            ),
            destination=resolve_relation_location_qualified_name(
                adapter=adapter, location=destination_location
            ),
            origin_is_transient=_location_is_transient(
                adapter=adapter, connection=destination_connection, location=origin_location
            ),
            statement_recorder=StatementRecorder(),
        )
    return "hydrated"


def hydrate_and_register_relation(
    *,
    adapter: BaseAdapter,
    destination_connection: Any,
    origin_location: CompiledRelationLocation,
    destination_location: CompiledRelationLocation,
    resource_kind: str,
    resource_name: str,
    run_id: str,
    register: Callable[[], None],
) -> str:
    """Hydrate fresh physical state and keep its attempt active through registration."""

    if adapter.relation_exists(
        connection=destination_connection,
        database=destination_location.database,
        schema=destination_location.schema,
        name=destination_location.name,
    ):
        register()
        return "reused"
    with ResourceAttemptLifecycle(
        resource_id=f"{resource_kind}:{resource_name}",
        resource_kind=resource_kind,
        resource_name=resource_name,
        run_id=run_id,
    ):
        action: str = hydrate_relation(
            adapter=adapter,
            destination_connection=destination_connection,
            origin_location=origin_location,
            destination_location=destination_location,
        )
        register()
        return action


def _location_is_transient(
    *, adapter: BaseAdapter, connection: Any, location: CompiledRelationLocation
) -> bool:
    """Return whether the origin warehouse relation is transient, defaulting to False."""

    if location.schema is None:
        return False
    relations: tuple[Any, ...] = adapter.list_relations(
        connection=connection,
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
            backend=backend,
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
        release_state_lease(
            backend=backend, connection=connection, schema=config_schema, lease=lease
        )
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
                connection=connection,
                schema=config_schema,
                model_name=model_version.model_name,
                version_hash=model_version.version_hash,
            )
            is None
        ):
            backend.upsert_model_version(
                connection=connection, schema=config_schema, record=model_version
            )
        if (
            backend.get_physical_relation(
                connection=connection,
                schema=config_schema,
                model_name=model.name,
                version_hash=model_version.version_hash,
            )
            is None
        ):
            backend.upsert_physical_relation(
                connection=connection,
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
                connection=connection,
                schema=config_schema,
                seed_name=seed_version.seed_name,
                version_hash=seed_version.version_hash,
            )
            is None
        ):
            backend.upsert_seed_version(
                connection=connection, schema=config_schema, record=seed_version
            )
        if (
            backend.get_physical_relation_for_artifact(
                connection=connection,
                schema=config_schema,
                artifact_type=PhysicalArtifactType.SEED,
                artifact_name=seed_version.seed_name,
                version_hash=seed_version.version_hash,
            )
            is None
        ):
            backend.upsert_physical_relation(
                connection=connection,
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


def compile_clone_pipeline(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    origin_target_name: str,
    destination_target_name: str,
    destination_connection: ClonePipelineConnection,
    no_sql_validation: bool,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    cli_vars: dict[str, object] | None,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None,
) -> ClonePipelineResult:
    """Compile origin and destination projects for one clone run."""

    return run_clone_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        origin_target_name=origin_target_name,
        destination_target_name=destination_target_name,
        no_sql_validation=no_sql_validation,
        select=select,
        exclude=exclude,
        cli_vars=cli_vars,
        destination_connection=destination_connection,
        external_sql_reference_resolver=external_sql_reference_resolver,
    )


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
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    clone_pipeline: ClonePipelineResult,
    context: CloneProjectContext,
    virtual_environment_name: str | None,
    discovered_inputs: DiscoveredProjectInputs,
    project_dir: Path,
    origin_target_name: str,
) -> CloneVersions:
    """Resolve model and seed version records to hydrate."""

    if virtual_environment_name is None:
        origin_schema: str | None = resolve_target_config(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
            target_name=origin_target_name,
        ).state.schema
        if origin_schema is None:
            raise StateBackendConfigError(
                f"Target '{origin_target_name}' state config must define schema"
            )
        return _resolve_workspace_clone_versions(
            clone_pipeline=clone_pipeline,
            context=context,
            backend=backend,
            state_connection=state_connection,
            schema=origin_schema,
            origin_virtual_environment_name=origin_target_name,
        )
    return _read_virtual_environment_clone_versions(
        backend=backend,
        state_connection=state_connection,
        schema=schema,
        context=context,
        virtual_environment_name=virtual_environment_name,
    )


def build_clone_origin_lookup(
    *,
    adapter: BaseAdapter,
    destination_connection: Any,
    context: CloneProjectContext,
    versions: CloneVersions,
) -> CloneOriginLookup:
    """Build origin lookup locations and the relation existence lookup."""

    model_locations: dict[str, CompiledRelationLocation] = {
        model_name: build_physical_destination(
            adapter=adapter,
            target=context.origin_models_by_name[model_name].destination,
            model_name=model_name,
            version_hash=versions.version_hashes[model_name],
        )
        for model_name in context.model_names
    }
    seed_locations: dict[str, CompiledRelationLocation] = {
        seed_name: build_physical_seed_destination(
            adapter=adapter,
            target=context.origin_seeds_by_name[seed_name].destination,
            seed_name=seed_name,
            version_hash=versions.seed_versions[seed_name].version_hash,
        )
        for seed_name in context.seed_names
    }
    with OperationLifecycle(
        operation_kind="clone", operation_name="clone_relation_inspection"
    ) as inspection:
        lookup: RelationLookup = build_relation_lookup(
            adapter=adapter,
            connection=destination_connection,
            locations=tuple(
                (location.database, location.schema, location.name)
                for location in (*model_locations.values(), *seed_locations.values())
            ),
        )
        inspection.completed(metadata={"item_count": len(model_locations) + len(seed_locations)})
    return CloneOriginLookup(
        model_locations=model_locations,
        seed_locations=seed_locations,
        lookup=lookup,
    )


def hydrate_clone_model_relations(
    *,
    backend: Any,
    adapter: BaseAdapter,
    destination_connection: Any,
    config_schema: str,
    config_connection: Any,
    context: CloneProjectContext,
    versions: CloneVersions,
    origin_lookup: CloneOriginLookup,
    skip_locked: bool,
    run_id: str,
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
            action: str = hydrate_and_register_relation(
                adapter=adapter,
                destination_connection=destination_connection,
                origin_location=origin_location,
                destination_location=destination_location,
                resource_kind="model",
                resource_name=model_name,
                run_id=run_id,
                register=partial(
                    register_hydrated_relation,
                    backend=backend,
                    config_schema=config_schema,
                    config_connection=config_connection,
                    model_version=versions.model_versions[model_name],
                    model=destination_model,
                    destination=destination_location,
                ),
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
    *,
    backend: Any,
    adapter: BaseAdapter,
    destination_connection: Any,
    config_schema: str,
    config_connection: Any,
    context: CloneProjectContext,
    versions: CloneVersions,
    origin_lookup: CloneOriginLookup,
    run_id: str,
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
        action: str = hydrate_and_register_relation(
            adapter=adapter,
            destination_connection=destination_connection,
            origin_location=origin_location,
            destination_location=destination_location,
            resource_kind="seed",
            resource_name=seed_name,
            run_id=run_id,
            register=partial(
                register_hydrated_seed_relation,
                backend=backend,
                config_schema=config_schema,
                config_connection=config_connection,
                seed_version=seed_version,
                destination=destination_location,
            ),
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
    backend: Any,
    state_connection: Any,
    schema: str,
    origin_virtual_environment_name: str,
) -> CloneVersions:
    semantics: VirtualPlanSemantics = build_virtual_plan_semantics(
        graph=context.destination_graph,
        bound_refs=(),
        bound_model_versions={},
    )
    version_hashes: dict[str, str] = dict(semantics.expected_version_hashes)
    model_versions: dict[str, ModelVersionRecord] = build_workspace_model_versions(
        project=clone_pipeline.destination_project,
        model_entries=clone_pipeline.destination_model_entries,
        model_names=context.model_names,
        version_hashes=version_hashes,
        local_hashes=semantics.expected_local_hashes,
        metadata_jsons=semantics.expected_metadata_jsons,
    )
    source_dependent_names: tuple[str, ...] = tuple(
        name
        for name in context.model_names
        if name in semantics.source_freshness_incomplete_model_names
    )
    if source_dependent_names:
        origin_refs: tuple[VirtualEnvironmentModelRefRecord, ...] = (
            backend.get_virtual_environment_model_refs(
                connection=state_connection,
                schema=schema,
                virtual_environment_name=origin_virtual_environment_name,
            )
        )
        origin_hashes: dict[str, str] = {ref.model_name: ref.version_hash for ref in origin_refs}
        missing_origin_refs: tuple[str, ...] = tuple(
            name for name in source_dependent_names if name not in origin_hashes
        )
        if missing_origin_refs:
            raise PlannerInputError(
                "origin virtual state is required for source-dependent workspace clone models: "
                + ", ".join(missing_origin_refs),
                code="S021",
            )
        for name in source_dependent_names:
            version_hash: str = origin_hashes[name]
            version: ModelVersionRecord | None = backend.get_model_version(
                connection=state_connection,
                schema=schema,
                model_name=name,
                version_hash=version_hash,
            )
            if version is None:
                raise PlannerInputError(
                    "origin virtual state has a source-dependent ref without model version: "
                    + name,
                    code="S021",
                )
            version_hashes[name] = version_hash
            model_versions[name] = version
    seed_versions: dict[str, SeedVersionRecord] = build_workspace_seed_versions(
        project=clone_pipeline.destination_project,
        seed_entries=clone_pipeline.destination_seed_entries,
        seed_names=context.seed_names,
        version_hashes=semantics.expected_seed_version_hashes,
        metadata_jsons=semantics.seed_identity_metadata_jsons,
    )
    return CloneVersions(
        mode=(
            "workspace fingerprints + origin VDE refs"
            if source_dependent_names
            else "workspace fingerprints"
        ),
        version_hashes=version_hashes,
        model_versions=model_versions,
        seed_versions=seed_versions,
        origin_state_used=bool(source_dependent_names),
    )


def _read_virtual_environment_clone_versions(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    context: CloneProjectContext,
    virtual_environment_name: str,
) -> CloneVersions:
    refs: tuple[VirtualEnvironmentModelRefRecord, ...] = backend.get_virtual_environment_model_refs(
        connection=state_connection,
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
            connection=state_connection,
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
            connection=state_connection,
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
            connection=state_connection,
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
