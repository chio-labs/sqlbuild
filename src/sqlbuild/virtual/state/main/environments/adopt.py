"""Public state adopt entrypoint."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.virtual.state._helpers.adopt import adopt_into_virtual_state
from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.models import StateBackendConfig


def run_state_adopt(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    config: StateBackendConfig,
    backend: StateBackend,
    state_connection: Any,
    adapter: BaseAdapter,
    connection: Any,
    allow_copy: bool = False,
) -> str:
    """Adopt existing stateless targets into virtual state and logical views."""

    return adopt_into_virtual_state(
        discovered_inputs=discovered_inputs,
        config=config,
        backend=backend,
        state_connection=state_connection,
        adapter=adapter,
        connection=connection,
        allow_copy=allow_copy,
    )
