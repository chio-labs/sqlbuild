"""Public checkpoint helpers for virtual targets."""

from __future__ import annotations

from typing import Any

from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.main.checkpoints._build_finalized_checkpoint import (
    build_finalized_virtual_environment_checkpoint,
)
from sqlbuild.virtual.state.models import (
    FinalizedVirtualEnvironmentCheckpoint,
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

    payload: FinalizedVirtualEnvironmentCheckpoint = build_finalized_virtual_environment_checkpoint(
        virtual_environment_name=virtual_environment_name,
        refs=refs,
        function_refs=function_refs,
        seed_refs=seed_refs,
    )
    backend.create_virtual_environment_checkpoint(
        connection=connection,
        schema=schema,
        checkpoint=payload.checkpoint,
        refs=payload.refs,
        function_refs=payload.function_refs,
        seed_refs=payload.seed_refs,
    )
    return payload.checkpoint.checkpoint_id
