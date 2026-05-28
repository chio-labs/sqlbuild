"""Detached virtual environment retention helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlbuild.virtual.state.models import (
    DetachedVirtualEnvironmentInspection,
    PhysicalRelationRecord,
    VirtualEnvironmentRefRecord,
    VirtualEnvironmentRetentionRecord,
)
from sqlbuild.virtual.state.types import VirtualEnvironmentStatus


def build_detached_environment_inspection(
    *,
    environments: tuple[VirtualEnvironmentRetentionRecord, ...],
    refs_by_environment: dict[str, tuple[VirtualEnvironmentRefRecord, ...]],
    physical_relations_by_ref: dict[tuple[str, str], PhysicalRelationRecord],
    retention_days: int,
    now: datetime,
) -> DetachedVirtualEnvironmentInspection:
    """Classify detached cleanup candidates and retained physical relation refs."""

    cleanup_names: set[str] = {
        environment.virtual_environment_name
        for environment in environments
        if _eligible_for_cleanup(
            environment=environment,
            retention_days=retention_days,
            now=now,
        )
    }
    cleanup_relations: dict[tuple[str | None, str, str], PhysicalRelationRecord] = {}
    retained_relations: dict[tuple[str | None, str, str], PhysicalRelationRecord] = {}
    environment: VirtualEnvironmentRetentionRecord
    for environment in environments:
        refs: tuple[VirtualEnvironmentRefRecord, ...] = refs_by_environment.get(
            environment.virtual_environment_name,
            (),
        )
        ref: VirtualEnvironmentRefRecord
        for ref in refs:
            relation: PhysicalRelationRecord | None = physical_relations_by_ref.get(
                (ref.model_name, ref.version_hash)
            )
            if relation is None:
                continue
            relation_key: tuple[str | None, str, str] = (
                relation.database_name,
                relation.schema_name,
                relation.relation_name,
            )
            if environment.virtual_environment_name in cleanup_names:
                cleanup_relations[relation_key] = relation
                continue
            retained_relations[relation_key] = relation
    return DetachedVirtualEnvironmentInspection(
        cleanup_virtual_environments=tuple(
            environment
            for environment in environments
            if environment.virtual_environment_name in cleanup_names
        ),
        cleanup_physical_relations=tuple(
            cleanup_relations[key]
            for key in sorted(cleanup_relations, key=lambda item: (item[0] or "", item[1], item[2]))
        ),
        retained_physical_relations=tuple(
            retained_relations[key]
            for key in sorted(
                retained_relations, key=lambda item: (item[0] or "", item[1], item[2])
            )
        ),
    )


def _eligible_for_cleanup(
    *, environment: VirtualEnvironmentRetentionRecord, retention_days: int, now: datetime
) -> bool:
    if environment.status != VirtualEnvironmentStatus.DETACHED:
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
