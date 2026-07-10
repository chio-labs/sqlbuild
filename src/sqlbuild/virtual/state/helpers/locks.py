"""State lock helper services."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.constants import STATE_MIGRATION_LOCK_KEY
from sqlbuild.virtual.state.models import StateLockLease


def virtual_environment_lock_key(virtual_environment_name: str) -> str:
    """Return the lock key for a virtual environment mutation."""

    return f"virtual_env:{virtual_environment_name}"


def model_version_lock_key(model_name: str, *, version_hash: str) -> str:
    """Return the lock key for a physical model version mutation."""

    return f"model_version:{model_name}:{version_hash}"


def acquire_virtual_environment_lock(
    backend: StateBackend,
    *,
    connection: Any,
    schema: str,
    virtual_environment_name: str,
    owner_id: str,
    ttl: timedelta,
    now: datetime | None = None,
) -> StateLockLease | None:
    """Acquire the lock for a virtual environment mutation."""

    return acquire_state_lock(
        backend,
        connection=connection,
        schema=schema,
        lock_key=virtual_environment_lock_key(virtual_environment_name),
        owner_id=owner_id,
        ttl=ttl,
        now=now,
    )


def acquire_model_version_lock(
    backend: StateBackend,
    *,
    connection: Any,
    schema: str,
    model_name: str,
    version_hash: str,
    owner_id: str,
    ttl: timedelta,
    now: datetime | None = None,
) -> StateLockLease | None:
    """Acquire the lock for a physical model version mutation."""

    return acquire_state_lock(
        backend,
        connection=connection,
        schema=schema,
        lock_key=model_version_lock_key(model_name, version_hash=version_hash),
        owner_id=owner_id,
        ttl=ttl,
        now=now,
    )


def acquire_state_migration_lock(
    backend: StateBackend,
    *,
    connection: Any,
    schema: str,
    owner_id: str,
    ttl: timedelta,
    now: datetime | None = None,
) -> StateLockLease | None:
    """Acquire the lock for state schema lifecycle operations."""

    return acquire_state_lock(
        backend,
        connection=connection,
        schema=schema,
        lock_key=STATE_MIGRATION_LOCK_KEY,
        owner_id=owner_id,
        ttl=ttl,
        now=now,
    )


def acquire_state_lock(
    backend: StateBackend,
    *,
    connection: Any,
    schema: str,
    lock_key: str,
    owner_id: str,
    ttl: timedelta,
    now: datetime | None = None,
) -> StateLockLease | None:
    """Acquire a state lock and return a lease when successful."""

    base_time: datetime = now or datetime.now()
    expires_at: datetime = base_time + ttl
    acquired: bool = backend.acquire_lock(
        connection,
        schema=schema,
        lock_key=lock_key,
        owner_id=owner_id,
        expires_at=expires_at,
    )
    if not acquired:
        return None
    return StateLockLease(lock_key=lock_key, owner_id=owner_id, expires_at=expires_at)


def release_state_lock(
    backend: StateBackend,
    *,
    connection: Any,
    schema: str,
    lease: StateLockLease,
) -> bool:
    """Release a previously acquired state lock lease."""

    return backend.release_lock(
        connection,
        schema=schema,
        lock_key=lease.lock_key,
        owner_id=lease.owner_id,
    )
