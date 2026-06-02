"""Janitor checkpoint planning helpers."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.executor.janitor.models import JanitorCheckpointCandidate, JanitorRelationKey
from sqlbuild.virtual.state.main.checkpoint_retention import inspect_checkpoint_retention
from sqlbuild.virtual.state.models import CheckpointRetentionInspection, PhysicalRelationRecord


def checkpoint_retention(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    virtual_environment_name: str | None,
) -> CheckpointRetentionInspection | None:
    """Inspect virtual checkpoint retention when janitor runs in virtual mode."""

    if not discovered_inputs.project_config.settings.virtual_environments:
        return None
    if virtual_environment_name is None:
        return None
    return inspect_checkpoint_retention(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        virtual_environment_name=virtual_environment_name,
        max_checkpoints=discovered_inputs.project_config.janitor.max_checkpoints,
    )


def checkpoint_protected_relation_keys(
    *,
    retention: CheckpointRetentionInspection | None,
) -> frozenset[JanitorRelationKey]:
    """Build janitor relation keys protected by retained checkpoints."""

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


def checkpoint_protected_relation_reasons(
    *,
    retention: CheckpointRetentionInspection | None,
) -> dict[JanitorRelationKey, str]:
    """Build protection reasons for retained checkpoint physical relations."""

    if retention is None:
        return {}
    return {
        JanitorRelationKey(
            database=relation.database_name,
            schema=relation.schema_name,
            name=relation.relation_name,
        ): "relation is referenced by a retained virtual checkpoint"
        for relation in retention.retained_physical_relations
    }


def checkpoint_candidates(
    *,
    retention: CheckpointRetentionInspection | None,
) -> tuple[JanitorCheckpointCandidate, ...]:
    """Build janitor checkpoint pruning candidates."""

    if retention is None:
        return ()
    return tuple(
        JanitorCheckpointCandidate(
            checkpoint_id=checkpoint.checkpoint_id,
            virtual_environment_name=checkpoint.virtual_environment_name,
            created_at=checkpoint.created_at,
        )
        for checkpoint in retention.prune_checkpoints
    )
