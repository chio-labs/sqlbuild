"""Public checkpoint list helper."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.virtual.state._helpers.backend import build_state_backend
from sqlbuild.virtual.state._helpers.config import resolve_state_backend_config
from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.models import StateBackendConfig, VirtualEnvironmentCheckpointRecord


def list_virtual_environment_checkpoints(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    virtual_environment_name: str,
) -> tuple[VirtualEnvironmentCheckpointRecord, ...]:
    """List checkpoints for a virtual environment."""

    config: StateBackendConfig = resolve_state_backend_config(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    backend: StateBackend = build_state_backend(config.backend)
    connection: Any = backend.connect(config.connection)
    try:
        return backend.list_virtual_environment_checkpoints(
            connection=connection,
            schema=config.schema,
            virtual_environment_name=virtual_environment_name,
        )
    finally:
        backend.close(connection)
