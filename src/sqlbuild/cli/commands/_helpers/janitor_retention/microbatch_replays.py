"""Janitor protection helpers for active virtual microbatch replays."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.executor.janitor.models import JanitorRelationKey
from sqlbuild.virtual.state.main.retention.microbatch_replay_retention import (
    inspect_active_microbatch_replay_relations,
)
from sqlbuild.virtual.state.models import PhysicalRelationRecord


def active_microbatch_replay_relations(
    *, project_dir: Path, discovered_inputs: DiscoveredProjectInputs
) -> tuple[PhysicalRelationRecord, ...]:
    """Inspect replay roots when janitor runs in virtual mode."""

    if not discovered_inputs.project_config.settings.virtual_environments:
        return ()
    return inspect_active_microbatch_replay_relations(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
    )


def active_microbatch_replay_protected_relation_keys(
    *, relations: tuple[PhysicalRelationRecord, ...]
) -> frozenset[JanitorRelationKey]:
    """Build relation keys protected by incomplete replay requirements."""

    return frozenset(_relation_key(relation) for relation in relations)


def active_microbatch_replay_protected_relation_reasons(
    *, relations: tuple[PhysicalRelationRecord, ...]
) -> dict[JanitorRelationKey, str]:
    """Build protection reasons for incomplete replay physical versions."""

    return {
        _relation_key(relation): "relation has an active microbatch replay requirement"
        for relation in relations
    }


def _relation_key(relation: PhysicalRelationRecord) -> JanitorRelationKey:
    return JanitorRelationKey(
        database=relation.database_name,
        schema=relation.schema_name,
        name=relation.relation_name,
    )
