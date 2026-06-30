"""Public virtual environment ref helper."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.virtual.state.helpers.runtime import build_state_runtime
from sqlbuild.virtual.state.models import VirtualEnvironmentModelRefRecord


def get_virtual_environment_model_refs(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    virtual_environment_name: str,
) -> tuple[VirtualEnvironmentModelRefRecord, ...]:
    """Get refs for a virtual environment."""

    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    connection: Any = backend.connect(config.connection)
    try:
        return backend.get_virtual_environment_model_refs(
            connection,
            schema=config.schema,
            virtual_environment_name=virtual_environment_name,
        )
    finally:
        backend.close(connection)
