"""Build virtual state runtime access."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.helpers.runtime import (
    build_state_runtime as _build_state_runtime,
)
from sqlbuild.virtual.state.models import StateBackendConfig


def build_state_runtime(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    project_dir: Path,
) -> tuple[StateBackendConfig, StateBackend]:
    """Resolve config and construct the configured virtual state backend."""

    return _build_state_runtime(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
