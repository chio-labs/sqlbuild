"""Public checkpoint helpers for virtual environments."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.models import (
    VirtualEnvironmentCheckpointRecord,
    VirtualEnvironmentCheckpointRefRecord,
    VirtualEnvironmentRefRecord,
)


def create_finalized_virtual_environment_checkpoint(
    backend: StateBackend,
    connection: Any,
    *,
    schema: str,
    virtual_environment_name: str,
    refs: tuple[VirtualEnvironmentRefRecord, ...],
) -> str:
    """Persist a finalized VDE checkpoint and return its checkpoint id."""

    timestamp: str = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    checkpoint_id: str = f"chk_{timestamp}_{uuid.uuid4().hex}"
    backend.create_virtual_environment_checkpoint(
        connection,
        schema=schema,
        checkpoint=VirtualEnvironmentCheckpointRecord(
            checkpoint_id=checkpoint_id,
            virtual_environment_name=virtual_environment_name,
        ),
        refs=tuple(
            VirtualEnvironmentCheckpointRefRecord(
                checkpoint_id=checkpoint_id,
                model_name=ref.model_name,
                version_hash=ref.version_hash,
            )
            for ref in refs
        ),
    )
    return checkpoint_id
