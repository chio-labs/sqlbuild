"""Build finalized virtual environment checkpoint rows."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlbuild.virtual.state.models import (
    FinalizedVirtualEnvironmentCheckpoint,
    VirtualEnvironmentCheckpointFunctionRefRecord,
    VirtualEnvironmentCheckpointModelRefRecord,
    VirtualEnvironmentCheckpointRecord,
    VirtualEnvironmentCheckpointSeedRefRecord,
    VirtualEnvironmentFunctionRefRecord,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentSeedRefRecord,
)


def build_finalized_virtual_environment_checkpoint(
    *,
    virtual_environment_name: str,
    refs: tuple[VirtualEnvironmentModelRefRecord, ...],
    function_refs: tuple[VirtualEnvironmentFunctionRefRecord, ...] = (),
    seed_refs: tuple[VirtualEnvironmentSeedRefRecord, ...] = (),
) -> FinalizedVirtualEnvironmentCheckpoint:
    """Build checkpoint rows for one finalized virtual environment."""

    timestamp: str = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    checkpoint_id: str = f"chk_{timestamp}_{uuid.uuid4().hex}"
    return FinalizedVirtualEnvironmentCheckpoint(
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
