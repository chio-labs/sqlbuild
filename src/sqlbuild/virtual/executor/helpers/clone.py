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
)
from sqlbuild.compiler.pipeline.main.project_graph import build_project_graph_from_compiled_project
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.shared.helpers.naming import (
    resolve_qualified_name_parts,
    resolve_relation_location_qualified_name,
)
from sqlbuild.virtual.executor.helpers.rewrite import relation_type_for_model
from sqlbuild.virtual.shared.helpers.encoding import encode_state_text
from sqlbuild.virtual.state.main.model_version_lock import acquire_model_version_lease
from sqlbuild.virtual.state.main.release_lock import release_state_lease
from sqlbuild.virtual.state.models import ModelVersionRecord, PhysicalRelationRecord, StateLockLease
from sqlbuild.virtual.state.types import ModelVersionStatus


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
            data_hash=local_hashes.get(name, version_hashes[name]),
            metadata_hash=hashlib.sha256(metadata_json.encode("utf-8")).hexdigest(),
            status=ModelVersionStatus.READY,
            fingerprint_query_sql_b64=encode_state_text(model.query_sql),
            fingerprint_metadata_json_b64=encode_state_text(metadata_json),
            compiled_sql_b64=encode_state_text(entry.resolved_sql) if entry is not None else None,
        )
    return records


def hydrate_relation(
    *,
    adapter: BaseAdapter,
    target_connection: Any,
    source_target: CompiledRelationLocation,
    target_target: CompiledRelationLocation,
    source_database_alias: str | None,
) -> str:
    if adapter.relation_exists(
        target_connection,
        database=target_target.database,
        schema=target_target.schema,
        name=target_target.name,
    ):
        return "reused"
    adapter.ensure_schema(
        target_connection,
        database=target_target.database,
        schema=target_target.schema or "",
        statement_recorder=StatementRecorder(),
    )
    clone_source_target: CompiledRelationLocation = (
        replace_target_database(
            adapter=adapter, target=source_target, database=source_database_alias
        )
        if source_database_alias is not None
        else source_target
    )
    adapter.durable_clone(
        target_connection,
        source=resolve_relation_location_qualified_name(
            adapter=adapter, location=clone_source_target
        ),
        target=resolve_relation_location_qualified_name(adapter=adapter, location=target_target),
        statement_recorder=StatementRecorder(),
    )
    return "hydrated"


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
    target: CompiledRelationLocation,
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
                    model_name=model.name,
                    version_hash=model_version.version_hash,
                    database_name=target.database,
                    schema_name=target.schema or "",
                    relation_name=target.name,
                    relation_type=relation_type_for_model(
                        MaterializationType(
                            model.config.values.get("materialized", MaterializationType.TABLE)
                        )
                    ),
                ),
            )
    finally:
        backend.close(connection)


def attach_source_database_for_clone(
    *,
    adapter: BaseAdapter,
    target_connection: Any,
    source_connection_config: dict[str, object],
    target_connection_config: dict[str, object],
) -> str | None:
    if adapter.adapter_name != BuiltinAdapter.DUCKDB:
        return None
    source_database: object | None = source_connection_config.get("database")
    target_database: object | None = target_connection_config.get("database")
    if source_database is None or source_database in {target_database, ":memory:"}:
        return None
    alias: str = "__sqb_clone_source"
    adapter.execute(
        target_connection,
        f"ATTACH '{str(source_database)}' AS {alias} (READ_ONLY)",
    )
    return alias


def replace_target_database(
    *, adapter: BaseAdapter, target: CompiledRelationLocation, database: str
) -> CompiledRelationLocation:
    return CompiledRelationLocation(
        database=database,
        schema=target.schema,
        name=target.name,
        qualified_name=resolve_qualified_name_parts(
            adapter=adapter, database=database, schema=target.schema, name=target.name
        ),
        logical_schema=target.logical_schema,
        logical_database=target.logical_database,
    )
