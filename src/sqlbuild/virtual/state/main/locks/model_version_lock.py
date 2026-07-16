"""Public model-version lock helper."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlbuild.virtual.state._helpers.state_storage.locks import acquire_model_version_lock
from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.models import StateLockLease


def acquire_model_version_lease(
    *,
    backend: StateBackend,
    connection: Any,
    schema: str,
    model_name: str,
    version_hash: str,
    owner_id: str,
    ttl: timedelta,
    now: datetime | None = None,
) -> StateLockLease | None:
    """Acquire a physical model version mutation lease."""

    return acquire_model_version_lock(
        backend=backend,
        connection=connection,
        schema=schema,
        model_name=model_name,
        version_hash=version_hash,
        owner_id=owner_id,
        ttl=ttl,
        now=now,
    )
