"""Public checkpoint ref helper."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.virtual.state._helpers.state_runtime.backend import build_state_backend
from sqlbuild.virtual.state._helpers.state_runtime.config import resolve_state_backend_config
from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.models import (
    StateBackendConfig,
    VirtualEnvironmentCheckpointModelRefRecord,
)


def get_virtual_environment_checkpoint_model_refs(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    checkpoint_id: str,
) -> tuple[VirtualEnvironmentCheckpointModelRefRecord, ...]:
    """Get refs for a virtual environment checkpoint."""

    config: StateBackendConfig = resolve_state_backend_config(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    backend: StateBackend = build_state_backend(config.backend)
    connection: Any = backend.connect(config.connection)
    try:
        return backend.get_virtual_environment_checkpoint_model_refs(
            connection=connection,
            schema=config.schema,
            checkpoint_id=checkpoint_id,
        )
    finally:
        backend.close(connection)
