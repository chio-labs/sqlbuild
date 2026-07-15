"""Runtime helpers for virtual state backend access."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.virtual.state._helpers.state_runtime.backend import build_state_backend
from sqlbuild.virtual.state._helpers.state_runtime.config import resolve_state_backend_config
from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.models import StateBackendConfig


def build_state_runtime(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    project_dir: Path,
) -> tuple[StateBackendConfig, StateBackend]:
    """Resolve config and construct the configured virtual state backend."""

    config: StateBackendConfig = resolve_state_backend_config(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    return config, build_state_backend(config.backend)
