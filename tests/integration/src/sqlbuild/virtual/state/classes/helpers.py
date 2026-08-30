from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, NamedTuple

from sqlbuild.virtual.state.classes.duckdb import DuckDbStateBackend
from sqlbuild.virtual.state.models import (
    VirtualEnvironmentCheckpointFunctionRefRecord,
    VirtualEnvironmentCheckpointModelRefRecord,
    VirtualEnvironmentCheckpointRecord,
    VirtualEnvironmentCheckpointSeedRefRecord,
    VirtualEnvironmentNodeRefRecord,
    VirtualEnvironmentRecord,
)
from sqlbuild.virtual.state.types import VirtualEnvironmentStatus

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
ORPHAN_CHECKPOINT_REFS_PAYLOAD: ConditionalPublicationPayload = VALID_PAYLOAD._replace(
    record=replace(VALID_PAYLOAD.record, status=VirtualEnvironmentStatus.FINALIZING),
    checkpoint=None,
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
