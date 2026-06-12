"""Public state-only janitor inspection helper."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.virtual.state.main.runtime import build_state_runtime
from sqlbuild.virtual.state.models import StateBackupRecord, StateJanitorInspection


def inspect_state_janitor_retention(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    retention_days: int,
) -> StateJanitorInspection:
    """Inspect state backup and expired-lock cleanup candidates."""

    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    connection: Any = backend.connect(config.connection)
    try:
        backups: tuple[StateBackupRecord, ...] = backend.list_state_backups(
            connection,
            schema=config.schema,
        )
        latest_backup_id: str | None = backups[0].backup_id if backups else None
        return StateJanitorInspection(
            schema=config.schema,
            state_backups=tuple(
                backup
                for backup in backups
                if backup.backup_id != latest_backup_id
                and _backup_is_eligible(
                    backup=backup,
                    retention_days=retention_days,
                    now=datetime.now(UTC),
                )
            ),
            expired_locks=backend.list_expired_locks(connection, schema=config.schema),
            unreferenced_python_node_versions=backend.count_unreferenced_python_node_versions(
                connection, schema=config.schema
            ),
        )
    finally:
        backend.close(connection)


def _backup_is_eligible(*, backup: StateBackupRecord, retention_days: int, now: datetime) -> bool:
    if retention_days == 0:
        return True
    if backup.created_at is None:
        return False
    return _aware(backup.created_at) <= _aware(now) - timedelta(days=retention_days)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
