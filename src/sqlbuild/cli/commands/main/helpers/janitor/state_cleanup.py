"""Janitor state-only cleanup helpers."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.executor.janitor.models import (
    JanitorExpiredLockCandidate,
    JanitorStateBackupCandidate,
)
from sqlbuild.virtual.state.main.state_janitor_retention import inspect_state_janitor_retention
from sqlbuild.virtual.state.models import StateJanitorInspection


def state_janitor_retention(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    retention_days: int,
) -> StateJanitorInspection | None:
    """Inspect state-only cleanup when janitor runs in virtual mode."""

    if not discovered_inputs.project_config.settings.virtual_environments:
        return None
    return inspect_state_janitor_retention(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        retention_days=retention_days,
    )


def state_backup_candidates(
    *,
    retention: StateJanitorInspection | None,
) -> tuple[JanitorStateBackupCandidate, ...]:
    """Build janitor state backup cleanup candidates."""

    if retention is None:
        return ()
    return tuple(
        JanitorStateBackupCandidate(
            backup_id=backup.backup_id,
            schema_name=backup.schema_name,
            created_at=backup.created_at,
        )
        for backup in retention.state_backups
    )


def expired_lock_candidates(
    *,
    retention: StateJanitorInspection | None,
) -> tuple[JanitorExpiredLockCandidate, ...]:
    """Build janitor expired lock cleanup candidates."""

    if retention is None:
        return ()
    return tuple(
        JanitorExpiredLockCandidate(
            lock_key=lock.lock_key,
            owner_id=lock.owner_id,
            expires_at=lock.expires_at,
        )
        for lock in retention.expired_locks
    )
