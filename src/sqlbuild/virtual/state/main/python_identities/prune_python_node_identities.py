"""Prune unreferenced Python node identity versions from virtual state."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.virtual.state.helpers.runtime import build_state_runtime


def prune_unreferenced_python_node_versions(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
) -> int:
    """Delete Python identity versions no VDE currently references."""

    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    connection: Any = backend.connect(config.connection)
    try:
        return backend.prune_unreferenced_python_node_versions(
            connection=connection,
            schema=config.schema,
        )
    finally:
        backend.close(connection)
