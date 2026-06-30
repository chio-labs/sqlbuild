"""Public checkpoint deletion helper."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.virtual.state.main.operations.runtime import build_state_runtime


def delete_virtual_environment_checkpoint(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    checkpoint_id: str,
) -> None:
    """Delete one virtual environment checkpoint and its refs."""

    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    connection: Any = backend.connect(config.connection)
    try:
        backend.delete_virtual_environment_checkpoint(
            connection,
            schema=config.schema,
            checkpoint_id=checkpoint_id,
        )
    finally:
        backend.close(connection)
