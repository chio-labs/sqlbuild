"""Public state lock helpers."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.helpers.locks import acquire_virtual_environment_lock
from sqlbuild.virtual.state.models import StateLockLease


def acquire_virtual_environment_lease(
    backend: StateBackend,
    connection: Any,
    *,
    schema: str,
    virtual_environment_name: str,
    owner_id: str,
    ttl: timedelta,
    now: datetime | None = None,
) -> StateLockLease | None:
    """Acquire a virtual environment mutation lease."""

    return acquire_virtual_environment_lock(
        backend,
        connection,
        schema=schema,
        virtual_environment_name=virtual_environment_name,
        owner_id=owner_id,
        ttl=ttl,
        now=now,
    )
