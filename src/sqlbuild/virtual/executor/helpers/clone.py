"""Virtual clone helper operations."""

from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.adapter.shared.types import BuiltinAdapter
from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledProject,
    CompiledRelationLocation,
    CompiledSeed,
)
from sqlbuild.compiler.pipeline.main.project_graph import build_project_graph_from_compiled_project
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.models import ModelPlanEntry, SeedPlanEntry
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.shared.helpers.naming import (
    resolve_qualified_name_parts,
    resolve_relation_location_qualified_name,
)
from sqlbuild.virtual.executor.helpers.rewrite import relation_type_for_model
from sqlbuild.virtual.shared.helpers.encoding import encode_state_text
from sqlbuild.virtual.state.main.model_version_lock import acquire_model_version_lease
from sqlbuild.virtual.state.main.release_lock import release_state_lease
from sqlbuild.virtual.state.models import (
    ModelVersionRecord,
    PhysicalRelationRecord,
    SeedVersionRecord,
    StateLockLease,
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
            connection,
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
        release_state_lease(backend, connection, schema=config_schema, lease=lease)
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
        f"ATTACH '{str(origin_database)}' AS {alias} (READ_ONLY)",
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
