"""Virtual planner entrypoint for Python identity state."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.spec.contracts.main.resolve_target_name import resolve_target_name
from sqlbuild.virtual.state.main.environments.runtime import build_state_runtime
from sqlbuild.virtual.state.main.python_identities._python_node_identity_read import (
    read_virtual_python_identity_fingerprints,
)


def read_bound_virtual_python_identities(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    project_dir: Path,
    virtual_environment_name: str | None,
) -> dict[tuple[str, str], Fingerprint]:
    """Read Python identity rows bound to the active virtual environment."""

    target_name: str | None = virtual_environment_name or resolve_target_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_target=None,
    )
    if target_name is None:
        return {}
    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    state_connection: Any = backend.connect(config.connection)
    try:
        return read_virtual_python_identity_fingerprints(
            backend=backend,
            state_connection=state_connection,
            schema=config.schema,
            virtual_environment_name=target_name,
        )
    finally:
        backend.close(state_connection)
