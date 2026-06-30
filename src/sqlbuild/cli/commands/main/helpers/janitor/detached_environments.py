"""Janitor detached VDE planning helpers."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.executor.janitor.models import (
    JanitorDetachedVirtualEnvironmentCandidate,
    JanitorRelationKey,
)
from sqlbuild.virtual.state.main.retention.detached_environment_retention import (
    inspect_detached_environment_retention,
)
from sqlbuild.virtual.state.models import (
    DetachedVirtualEnvironmentInspection,
    PhysicalRelationRecord,
)


def detached_environment_retention(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    retention_days: int,
) -> DetachedVirtualEnvironmentInspection | None:
    """Inspect detached VDE cleanup when janitor runs in virtual mode."""

    if not discovered_inputs.project_config.settings.virtual_environments:
        return None
    return inspect_detached_environment_retention(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        retention_days=retention_days,
    )


def detached_environment_protected_relation_keys(
    *,
    retention: DetachedVirtualEnvironmentInspection | None,
) -> frozenset[JanitorRelationKey]:
    """Build janitor relation keys protected by retained VDE current refs."""

    if retention is None:
        return frozenset()
    relations: tuple[PhysicalRelationRecord, ...] = retention.retained_physical_relations
    return frozenset(
        JanitorRelationKey(
            database=relation.database_name,
            schema=relation.schema_name,
            name=relation.relation_name,
        )
        for relation in relations
    )


def detached_environment_scan_relation_keys(
    *,
    retention: DetachedVirtualEnvironmentInspection | None,
) -> frozenset[JanitorRelationKey]:
    """Build relation keys whose schemas must be scanned for detached VDE cleanup."""

    if retention is None:
        return frozenset()
    return frozenset(
        JanitorRelationKey(
            database=relation.database_name,
            schema=relation.schema_name,
            name=relation.relation_name,
        )
        for relation in retention.cleanup_physical_relations
    )


def detached_environment_protected_relation_reasons(
    *,
    retention: DetachedVirtualEnvironmentInspection | None,
) -> dict[JanitorRelationKey, str]:
    """Build protection reasons for retained VDE current-ref physical relations."""

    if retention is None:
        return {}
    return {
        JanitorRelationKey(
            database=relation.database_name,
            schema=relation.schema_name,
            name=relation.relation_name,
        ): "relation is referenced by an active or retained virtual environment"
        for relation in retention.retained_physical_relations
    }


def detached_environment_candidates(
    *,
    retention: DetachedVirtualEnvironmentInspection | None,
) -> tuple[JanitorDetachedVirtualEnvironmentCandidate, ...]:
    """Build janitor detached VDE cleanup candidates."""

    if retention is None:
        return ()
    return tuple(
        JanitorDetachedVirtualEnvironmentCandidate(
            virtual_environment_name=environment.virtual_environment_name,
            updated_at=environment.updated_at,
        )
        for environment in retention.cleanup_virtual_environments
    )
