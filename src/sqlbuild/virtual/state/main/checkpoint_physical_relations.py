"""Public helper for physical relations referenced by retained checkpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.virtual.state.main.runtime import build_state_runtime
from sqlbuild.virtual.state.models import (
    PhysicalRelationRecord,
    VirtualEnvironmentCheckpointRecord,
    VirtualEnvironmentCheckpointRefRecord,
)


def list_checkpoint_physical_relations(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    virtual_environment_name: str,
) -> tuple[PhysicalRelationRecord, ...]:
    """List physical relations referenced by retained checkpoints for a VDE."""

    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    connection: Any = backend.connect(config.connection)
    try:
        checkpoints: tuple[VirtualEnvironmentCheckpointRecord, ...] = (
            backend.list_virtual_environment_checkpoints(
                connection,
                schema=config.schema,
                virtual_environment_name=virtual_environment_name,
            )
        )
        relations: dict[tuple[str | None, str | None, str], PhysicalRelationRecord] = {}
        checkpoint: VirtualEnvironmentCheckpointRecord
        for checkpoint in checkpoints:
            refs: tuple[VirtualEnvironmentCheckpointRefRecord, ...] = (
                backend.get_virtual_environment_checkpoint_refs(
                    connection,
                    schema=config.schema,
                    checkpoint_id=checkpoint.checkpoint_id,
                )
            )
            ref: VirtualEnvironmentCheckpointRefRecord
            for ref in refs:
                relation: PhysicalRelationRecord | None = backend.get_physical_relation(
                    connection,
                    schema=config.schema,
                    model_name=ref.model_name,
                    version_hash=ref.version_hash,
                )
                if relation is None:
                    continue
                relations[
                    (relation.database_name, relation.schema_name, relation.relation_name)
                ] = relation
        return tuple(relations[key] for key in sorted(relations))
    finally:
        backend.close(connection)
