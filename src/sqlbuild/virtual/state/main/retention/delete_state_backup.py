"""Public state backup deletion helper."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.virtual.state.helpers.runtime import build_state_runtime


def delete_state_backup(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    backup_id: str,
) -> None:
    """Delete one state migration backup schema."""

    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    connection: Any = backend.connect(config.connection)
    try:
        backend.delete_state_backup(
            connection=connection, schema=config.schema, backup_id=backup_id
        )
    finally:
        backend.close(connection)
