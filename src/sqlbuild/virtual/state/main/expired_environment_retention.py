"""Public expired VDE retention inspection helper."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.virtual.state.main.runtime import build_state_runtime
from sqlbuild.virtual.state.models import (
    ExpiredVirtualEnvironmentInspection,
    PhysicalRelationRecord,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentRetentionRecord,
)
from sqlbuild.virtual.state.types import VirtualEnvironmentStatus


def inspect_expired_environment_retention(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    active_virtual_environment_name: str | None,
    retention_days: int,
) -> ExpiredVirtualEnvironmentInspection:
    """Inspect non-active VDE cleanup and retained current-ref physical relations."""

    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    connection: Any = backend.connect(config.connection)
    try:
        environments: tuple[VirtualEnvironmentRetentionRecord, ...] = (
            backend.list_virtual_environments(connection, schema=config.schema)
        )
        cleanup_names: set[str] = {
            environment.virtual_environment_name
            for environment in environments
            if _eligible_for_cleanup(
                environment=environment,
                active_virtual_environment_name=active_virtual_environment_name,
                retention_days=retention_days,
                now=datetime.now(UTC),
            )
        }
        cleanup_relations: dict[tuple[str | None, str, str], PhysicalRelationRecord] = {}
        retained_relations: dict[tuple[str | None, str, str], PhysicalRelationRecord] = {}
        for environment in environments:
            if environment.status == VirtualEnvironmentStatus.DETACHED:
                continue
            refs: tuple[VirtualEnvironmentModelRefRecord, ...] = (
                backend.get_virtual_environment_model_refs(
                    connection,
                    schema=config.schema,
                    virtual_environment_name=environment.virtual_environment_name,
                )
            )
            for ref in refs:
                relation: PhysicalRelationRecord | None = backend.get_physical_relation(
                    connection,
                    schema=config.schema,
                    model_name=ref.model_name,
                    version_hash=ref.version_hash,
                )
                if relation is None:
                    continue
                key: tuple[str | None, str, str] = (
                    relation.database_name,
                    relation.schema_name,
                    relation.relation_name,
                )
                if environment.virtual_environment_name in cleanup_names:
                    cleanup_relations[key] = relation
                else:
                    retained_relations[key] = relation
        return ExpiredVirtualEnvironmentInspection(
            cleanup_virtual_environments=tuple(
                environment
                for environment in environments
                if environment.virtual_environment_name in cleanup_names
            ),
            cleanup_physical_relations=tuple(
                cleanup_relations[key]
                for key in sorted(
                    cleanup_relations, key=lambda item: (item[0] or "", item[1], item[2])
                )
            ),
            retained_physical_relations=tuple(
                retained_relations[key]
                for key in sorted(
                    retained_relations, key=lambda item: (item[0] or "", item[1], item[2])
                )
            ),
        )
    finally:
        backend.close(connection)


def _eligible_for_cleanup(
    *,
    environment: VirtualEnvironmentRetentionRecord,
    active_virtual_environment_name: str | None,
    retention_days: int,
    now: datetime,
) -> bool:
    if environment.virtual_environment_name == active_virtual_environment_name:
        return False
    if environment.status == VirtualEnvironmentStatus.DETACHED:
        return False
    if retention_days == 0:
        return True
    if environment.updated_at is None:
        return False
    return _aware(environment.updated_at) <= _aware(now) - timedelta(days=retention_days)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
