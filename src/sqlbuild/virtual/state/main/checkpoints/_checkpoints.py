"""Public checkpoint helpers for virtual targets."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.models import (
    VirtualEnvironmentCheckpointFunctionRefRecord,
    VirtualEnvironmentCheckpointModelRefRecord,
    VirtualEnvironmentCheckpointRecord,
    VirtualEnvironmentCheckpointSeedRefRecord,
    VirtualEnvironmentFunctionRefRecord,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentSeedRefRecord,
)


def create_finalized_virtual_environment_checkpoint(
    *,
    backend: StateBackend,
    connection: Any,
    schema: str,
    virtual_environment_name: str,
    refs: tuple[VirtualEnvironmentModelRefRecord, ...],
    function_refs: tuple[VirtualEnvironmentFunctionRefRecord, ...] = (),
    seed_refs: tuple[VirtualEnvironmentSeedRefRecord, ...] = (),
) -> str:
    """Persist a finalized VDE checkpoint and return its checkpoint id."""

    timestamp: str = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    checkpoint_id: str = f"chk_{timestamp}_{uuid.uuid4().hex}"
    backend.create_virtual_environment_checkpoint(
        connection=connection,
        schema=schema,
        checkpoint=VirtualEnvironmentCheckpointRecord(
            checkpoint_id=checkpoint_id,
            virtual_environment_name=virtual_environment_name,
        ),
        refs=tuple(
            VirtualEnvironmentCheckpointModelRefRecord(
                checkpoint_id=checkpoint_id,
                model_name=ref.model_name,
                version_hash=ref.version_hash,
            )
            for ref in refs
        ),
        function_refs=tuple(
            VirtualEnvironmentCheckpointFunctionRefRecord(
                checkpoint_id=checkpoint_id,
                function_name=ref.function_name,
                version_hash=ref.version_hash,
            )
            for ref in function_refs
        ),
        seed_refs=tuple(
            VirtualEnvironmentCheckpointSeedRefRecord(
                checkpoint_id=checkpoint_id,
                seed_name=ref.seed_name,
                version_hash=ref.version_hash,
            )
            for ref in seed_refs
        ),
    )
    return checkpoint_id
