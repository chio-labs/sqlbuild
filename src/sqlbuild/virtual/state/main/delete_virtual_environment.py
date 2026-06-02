"""Public virtual environment deletion helper."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.virtual.state.main.runtime import build_state_runtime


def delete_virtual_environment(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    virtual_target_name: str,
) -> None:
    """Delete one virtual environment and its current refs."""

    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    connection: Any = backend.connect(config.connection)
    try:
        backend.delete_virtual_environment(
            connection,
            schema=config.schema,
            virtual_target_name=virtual_target_name,
        )
    finally:
        backend.close(connection)
