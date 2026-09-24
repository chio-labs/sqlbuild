from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, NamedTuple

from sqlbuild.virtual.state.classes.duckdb import DuckDbStateBackend
from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.models import (
    FunctionVersionRecord,
    PhysicalRelationRecord,
    VirtualEnvironmentCheckpointFunctionRefRecord,
    VirtualEnvironmentCheckpointModelRefRecord,
    VirtualEnvironmentCheckpointRecord,
    VirtualEnvironmentCheckpointSeedRefRecord,
    VirtualEnvironmentNodeRefRecord,
    VirtualEnvironmentRecord,
)
from sqlbuild.virtual.state.types import (
    ModelVersionStatus,
    PhysicalArtifactType,
    VirtualEnvironmentStatus,
)

_ENVIRONMENT: str = "dev"
_CHECKPOINT_ID: str = "checkpoint-1"
_CHECKPOINT: VirtualEnvironmentCheckpointRecord = VirtualEnvironmentCheckpointRecord(
    _CHECKPOINT_ID, _ENVIRONMENT
)


class ConditionalPublicationPayload(NamedTuple):
    """Arguments for one conditional environment publication call."""

    record: VirtualEnvironmentRecord
    refs_by_node_type: dict[str, tuple[VirtualEnvironmentNodeRefRecord, ...]]
    checkpoint: VirtualEnvironmentCheckpointRecord | None
    checkpoint_refs: tuple[VirtualEnvironmentCheckpointModelRefRecord, ...]
    checkpoint_function_refs: tuple[VirtualEnvironmentCheckpointFunctionRefRecord, ...]
    checkpoint_seed_refs: tuple[VirtualEnvironmentCheckpointSeedRefRecord, ...]


VALID_PAYLOAD: ConditionalPublicationPayload = ConditionalPublicationPayload(
    record=VirtualEnvironmentRecord(_ENVIRONMENT, VirtualEnvironmentStatus.FINALIZED),
    refs_by_node_type={
        "model": (VirtualEnvironmentNodeRefRecord(_ENVIRONMENT, "model", "orders", "model-v1"),),
        "udf": (VirtualEnvironmentNodeRefRecord(_ENVIRONMENT, "udf", "normalize", "function-v1"),),
        "seed": (VirtualEnvironmentNodeRefRecord(_ENVIRONMENT, "seed", "countries", "seed-v1"),),
    },
    checkpoint=_CHECKPOINT,
    checkpoint_refs=(
        VirtualEnvironmentCheckpointModelRefRecord(_CHECKPOINT_ID, "orders", "model-v1"),
    ),
    checkpoint_function_refs=(
        VirtualEnvironmentCheckpointFunctionRefRecord(_CHECKPOINT_ID, "normalize", "function-v1"),
    ),
    checkpoint_seed_refs=(
        VirtualEnvironmentCheckpointSeedRefRecord(_CHECKPOINT_ID, "countries", "seed-v1"),
    ),
)
ACTIVE_PAYLOAD: ConditionalPublicationPayload = VALID_PAYLOAD._replace(
    record=replace(VALID_PAYLOAD.record, status=VirtualEnvironmentStatus.ACTIVE),
    checkpoint=None,
    checkpoint_refs=(),
    checkpoint_function_refs=(),
    checkpoint_seed_refs=(),
)
MISSING_CHECKPOINT_PAYLOAD: ConditionalPublicationPayload = VALID_PAYLOAD._replace(
    checkpoint=None,
    checkpoint_refs=(),
    checkpoint_function_refs=(),
    checkpoint_seed_refs=(),
)
ACTIVE_CHECKPOINT_PAYLOAD: ConditionalPublicationPayload = VALID_PAYLOAD._replace(
    record=replace(VALID_PAYLOAD.record, status=VirtualEnvironmentStatus.ACTIVE)
)
FINALIZING_CHECKPOINT_PAYLOAD: ConditionalPublicationPayload = VALID_PAYLOAD._replace(
    record=replace(VALID_PAYLOAD.record, status=VirtualEnvironmentStatus.FINALIZING)
)
DETACHED_CHECKPOINT_PAYLOAD: ConditionalPublicationPayload = VALID_PAYLOAD._replace(
    record=replace(VALID_PAYLOAD.record, status=VirtualEnvironmentStatus.DETACHED)
)
FAILED_CHECKPOINT_PAYLOAD: ConditionalPublicationPayload = VALID_PAYLOAD._replace(
    record=replace(VALID_PAYLOAD.record, status=VirtualEnvironmentStatus.FAILED)
)
CHECKPOINT_ENVIRONMENT_PAYLOAD: ConditionalPublicationPayload = VALID_PAYLOAD._replace(
    checkpoint=replace(_CHECKPOINT, virtual_environment_name="other")
)
CHECKPOINT_ID_PAYLOAD: ConditionalPublicationPayload = VALID_PAYLOAD._replace(
    checkpoint_function_refs=(
        replace(VALID_PAYLOAD.checkpoint_function_refs[0], checkpoint_id="other"),
    )
)
MODEL_VERSION_PAYLOAD: ConditionalPublicationPayload = VALID_PAYLOAD._replace(
    checkpoint_refs=(replace(VALID_PAYLOAD.checkpoint_refs[0], version_hash="other"),)
)
FUNCTION_OMISSION_PAYLOAD: ConditionalPublicationPayload = VALID_PAYLOAD._replace(
    checkpoint_function_refs=()
)
SEED_EXTRA_PAYLOAD: ConditionalPublicationPayload = VALID_PAYLOAD._replace(
    checkpoint_seed_refs=(
        *VALID_PAYLOAD.checkpoint_seed_refs,
        VirtualEnvironmentCheckpointSeedRefRecord(_CHECKPOINT_ID, "extra", "seed-v2"),
    )
)
CHECKPOINT_DUPLICATE_PAYLOAD: ConditionalPublicationPayload = VALID_PAYLOAD._replace(
    checkpoint_refs=(*VALID_PAYLOAD.checkpoint_refs, *VALID_PAYLOAD.checkpoint_refs)
)
PUBLISHED_DUPLICATE_PAYLOAD: ConditionalPublicationPayload = VALID_PAYLOAD._replace(
    refs_by_node_type={
        **VALID_PAYLOAD.refs_by_node_type,
        "model": (
            *VALID_PAYLOAD.refs_by_node_type["model"],
            *VALID_PAYLOAD.refs_by_node_type["model"],
        ),
    }
)
REF_ENVIRONMENT_PAYLOAD: ConditionalPublicationPayload = VALID_PAYLOAD._replace(
    refs_by_node_type={
        **VALID_PAYLOAD.refs_by_node_type,
        "model": (
            replace(
                VALID_PAYLOAD.refs_by_node_type["model"][0],
                virtual_environment_name="other",
            ),
        ),
    }
)
REF_NODE_TYPE_PAYLOAD: ConditionalPublicationPayload = VALID_PAYLOAD._replace(
    refs_by_node_type={
        **VALID_PAYLOAD.refs_by_node_type,
        "model": (replace(VALID_PAYLOAD.refs_by_node_type["model"][0], node_type="seed"),),
    }
)


def open_duckdb_state_backend(*, db_path: Path) -> tuple[DuckDbStateBackend, Any]:
    backend: DuckDbStateBackend = DuckDbStateBackend()
    connection: Any = backend.connect({"database": str(db_path)})
    return backend, connection


def fetch_all(connection: Any, sql: str) -> list[tuple[Any, ...]]:
    return connection.execute(sql).fetchall()


STATE_READ_CONTRACT_FUNCTION: FunctionVersionRecord = FunctionVersionRecord(
    function_name="is_large_order",
    version_hash="function-v1",
    language="sql",
    returns="BOOLEAN",
    arguments_json_b64="W3sibmFtZSI6ImFtb3VudCIsInR5cGUiOiJJTlRFR0VSIn1d",
    return_columns_json_b64="W10=",
    packages_json_b64="W10=",
    runtime_version=None,
    entry_point=None,
    body_sql_b64="YW1vdW50ID4gOQ==",
    definition_text_b64="YW1vdW50ID4gOQ==",
    status=ModelVersionStatus.READY,
)
STATE_READ_CONTRACT_RELATION_V1: PhysicalRelationRecord = PhysicalRelationRecord(
    artifact_type=PhysicalArtifactType.MODEL,
    artifact_name="orders",
    version_hash="orders-v1",
    database_name=None,
    schema_name="sqb_orders",
    relation_name="orders__v1",
    relation_type="table",
)
STATE_READ_CONTRACT_RELATION_V2: PhysicalRelationRecord = replace(
    STATE_READ_CONTRACT_RELATION_V1, version_hash="orders-v2", relation_name="orders__v2"
)


class StateReadContractObservation(NamedTuple):
    """Values read back after writing the shared state read contract fixture."""

    function_before_upsert: FunctionVersionRecord | None
    function_after_upsert: FunctionVersionRecord | None
    function_after_second_upsert: FunctionVersionRecord | None
    relation_v1: PhysicalRelationRecord | None
    relation_missing: PhysicalRelationRecord | None
    relations: tuple[PhysicalRelationRecord, ...]
    environments: tuple[tuple[str, VirtualEnvironmentStatus], ...]
    active_lock_keys: tuple[str, ...]
    expired_lock_keys: tuple[str, ...]


def exercise_state_read_contract(
    *, backend: StateBackend, connection: Any, schema: str
) -> StateReadContractObservation:
    function_before_upsert: FunctionVersionRecord | None = backend.get_function_version(
        connection=connection,
        schema=schema,
        function_name=STATE_READ_CONTRACT_FUNCTION.function_name,
        version_hash=STATE_READ_CONTRACT_FUNCTION.version_hash,
    )
    backend.upsert_function_version(
        connection=connection, schema=schema, record=STATE_READ_CONTRACT_FUNCTION
    )
    function_after_upsert: FunctionVersionRecord | None = backend.get_function_version(
        connection=connection,
        schema=schema,
        function_name=STATE_READ_CONTRACT_FUNCTION.function_name,
        version_hash=STATE_READ_CONTRACT_FUNCTION.version_hash,
    )
    backend.upsert_function_version(
        connection=connection,
        schema=schema,
        record=replace(STATE_READ_CONTRACT_FUNCTION, status=ModelVersionStatus.FAILED),
    )
    function_after_second_upsert: FunctionVersionRecord | None = backend.get_function_version(
        connection=connection,
        schema=schema,
        function_name=STATE_READ_CONTRACT_FUNCTION.function_name,
        version_hash=STATE_READ_CONTRACT_FUNCTION.version_hash,
    )
    backend.upsert_physical_relation(
        connection=connection, schema=schema, record=STATE_READ_CONTRACT_RELATION_V1
    )
    backend.upsert_physical_relation(
        connection=connection, schema=schema, record=STATE_READ_CONTRACT_RELATION_V2
    )
    relation_v1: PhysicalRelationRecord | None = backend.get_physical_relation_for_artifact(
        connection=connection,
        schema=schema,
        artifact_type=PhysicalArtifactType.MODEL,
        artifact_name="orders",
        version_hash="orders-v1",
    )
    relation_missing: PhysicalRelationRecord | None = backend.get_physical_relation_for_artifact(
        connection=connection,
        schema=schema,
        artifact_type=PhysicalArtifactType.MODEL,
        artifact_name="orders",
        version_hash="orders-v3",
    )
    relations: tuple[PhysicalRelationRecord, ...] = backend.list_physical_relations_for_artifact(
        connection=connection,
        schema=schema,
        artifact_type=PhysicalArtifactType.MODEL,
        artifact_name="orders",
    )
    backend.upsert_virtual_environment(
        connection=connection,
        schema=schema,
        record=VirtualEnvironmentRecord("dev", VirtualEnvironmentStatus.ACTIVE),
    )
    backend.upsert_virtual_environment(
        connection=connection,
        schema=schema,
        record=VirtualEnvironmentRecord("prod", VirtualEnvironmentStatus.FINALIZED),
    )
    environments: tuple[tuple[str, VirtualEnvironmentStatus], ...] = tuple(
        (record.virtual_environment_name, record.status)
        for record in backend.list_virtual_environments(connection=connection, schema=schema)
    )
    backend.acquire_lock(
        connection=connection,
        schema=schema,
        lock_key="lock_expired",
        owner_id="run-1",
        expires_at=datetime.now() - timedelta(days=2),
    )
    backend.acquire_lock(
        connection=connection,
        schema=schema,
        lock_key="lock_active",
        owner_id="run-1",
        expires_at=datetime.now() + timedelta(days=2),
    )
    active_lock_keys: tuple[str, ...] = tuple(
        lock.lock_key for lock in backend.list_active_locks(connection=connection, schema=schema)
    )
    expired_lock_keys: tuple[str, ...] = tuple(
        lock.lock_key for lock in backend.list_expired_locks(connection=connection, schema=schema)
    )
    return StateReadContractObservation(
        function_before_upsert=function_before_upsert,
        function_after_upsert=function_after_upsert,
        function_after_second_upsert=function_after_second_upsert,
        relation_v1=relation_v1,
        relation_missing=relation_missing,
        relations=relations,
        environments=environments,
        active_lock_keys=active_lock_keys,
        expired_lock_keys=expired_lock_keys,
    )
