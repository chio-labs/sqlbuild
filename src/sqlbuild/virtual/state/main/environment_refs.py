"""Public virtual environment ref helper."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.virtual.state.main.runtime import build_state_runtime
from sqlbuild.virtual.state.models import VirtualEnvironmentRefRecord


def get_virtual_environment_refs(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    virtual_target_name: str,
) -> tuple[VirtualEnvironmentRefRecord, ...]:
    """Get refs for a virtual environment."""

    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    connection: Any = backend.connect(config.connection)
    try:
        return backend.get_virtual_environment_refs(
            connection,
            schema=config.schema,
            virtual_target_name=virtual_target_name,
        )
    finally:
        backend.close(connection)
