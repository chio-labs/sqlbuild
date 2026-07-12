"""Public state lock deletion helper."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.virtual.state.helpers.runtime import build_state_runtime


def delete_lock(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    lock_key: str,
) -> None:
    """Delete one state lock by key."""

    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    connection: Any = backend.connect(config.connection)
    try:
        backend.delete_lock(connection=connection, schema=config.schema, lock_key=lock_key)
    finally:
        backend.close(connection)
