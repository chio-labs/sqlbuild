"""Public checkpoint ref helper."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.helpers.backend import build_state_backend
from sqlbuild.virtual.state.helpers.config import resolve_state_backend_config
from sqlbuild.virtual.state.models import StateBackendConfig, VirtualEnvironmentCheckpointRefRecord


def get_virtual_environment_checkpoint_refs(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    checkpoint_id: str,
) -> tuple[VirtualEnvironmentCheckpointRefRecord, ...]:
    """Get refs for a virtual environment checkpoint."""

    config: StateBackendConfig = resolve_state_backend_config(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    backend: StateBackend = build_state_backend(config.backend)
    connection: Any = backend.connect(config.connection)
    try:
        return backend.get_virtual_environment_checkpoint_refs(
            connection,
            schema=config.schema,
            checkpoint_id=checkpoint_id,
        )
    finally:
        backend.close(connection)
