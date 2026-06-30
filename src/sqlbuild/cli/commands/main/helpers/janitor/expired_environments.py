"""Janitor expired VDE planning helpers."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.executor.janitor.models import (
    JanitorExpiredVirtualEnvironmentCandidate,
    JanitorRelationKey,
)
from sqlbuild.virtual.state.main.operations.expired_environment_retention import (
    inspect_expired_environment_retention,
)
from sqlbuild.virtual.state.models import (
    ExpiredVirtualEnvironmentInspection,
    PhysicalRelationRecord,
)


def expired_environment_retention(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    active_virtual_environment_name: str | None,
    retention_days: int,
) -> ExpiredVirtualEnvironmentInspection | None:
    """Inspect non-active VDE cleanup when janitor runs in virtual mode."""

    if not discovered_inputs.project_config.settings.virtual_environments:
        return None
    return inspect_expired_environment_retention(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        active_virtual_environment_name=active_virtual_environment_name,
        retention_days=retention_days,
    )


def expired_environment_protected_relation_keys(
    *,
    retention: ExpiredVirtualEnvironmentInspection | None,
) -> frozenset[JanitorRelationKey]:
    """Build relation keys protected by retained VDE current refs."""

    if retention is None:
        return frozenset()
    return frozenset(_relation_key(relation) for relation in retention.retained_physical_relations)


def expired_environment_scan_relation_keys(
    *,
    retention: ExpiredVirtualEnvironmentInspection | None,
) -> frozenset[JanitorRelationKey]:
    """Build relation keys whose schemas must be scanned for VDE cleanup."""

    if retention is None:
        return frozenset()
    return frozenset(_relation_key(relation) for relation in retention.cleanup_physical_relations)


def expired_environment_protected_relation_reasons(
    *,
    retention: ExpiredVirtualEnvironmentInspection | None,
) -> dict[JanitorRelationKey, str]:
    """Build protection reasons for retained VDE current-ref physical relations."""

    if retention is None:
        return {}
    return {
        _relation_key(relation): (
            "relation is referenced by an active or retained virtual environment"
        )
        for relation in retention.retained_physical_relations
    }


def expired_environment_candidates(
    *,
    retention: ExpiredVirtualEnvironmentInspection | None,
) -> tuple[JanitorExpiredVirtualEnvironmentCandidate, ...]:
    """Build janitor expired VDE cleanup candidates."""

    if retention is None:
        return ()
    return tuple(
        JanitorExpiredVirtualEnvironmentCandidate(
            virtual_environment_name=environment.virtual_environment_name,
            updated_at=environment.updated_at,
        )
        for environment in retention.cleanup_virtual_environments
    )


def _relation_key(relation: PhysicalRelationRecord) -> JanitorRelationKey:
    return JanitorRelationKey(
        database=relation.database_name,
        schema=relation.schema_name,
        name=relation.relation_name,
    )
