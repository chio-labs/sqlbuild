"""Public state lock release entrypoint."""

from __future__ import annotations

from typing import Any

from sqlbuild.virtual.state._helpers.state_storage.locks import release_state_lock
from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.models import StateLockLease


def release_state_lease(
    *,
    backend: StateBackend,
    connection: Any,
    schema: str,
    lease: StateLockLease,
) -> bool:
    """Release a state lock lease."""

    return release_state_lock(backend=backend, connection=connection, schema=schema, lease=lease)
