"""Public checkpoint retention inspection helper."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.virtual.state.helpers.runtime import build_state_runtime
from sqlbuild.virtual.state.models import (
    CheckpointRetentionInspection,
    PhysicalRelationRecord,
    VirtualEnvironmentCheckpointModelRefRecord,
    VirtualEnvironmentCheckpointRecord,
)


def inspect_checkpoint_retention(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    virtual_environment_name: str,
    max_checkpoints: int,
) -> CheckpointRetentionInspection:
    """Inspect checkpoint retention and retained checkpoint physical relations."""

    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    connection: Any = backend.connect(config.connection)
    try:
        checkpoints: tuple[VirtualEnvironmentCheckpointRecord, ...] = (
            backend.list_virtual_environment_checkpoints(
                connection=connection,
                schema=config.schema,
                virtual_environment_name=virtual_environment_name,
            )
        )
        retained_checkpoints: tuple[VirtualEnvironmentCheckpointRecord, ...] = checkpoints[
            :max_checkpoints
        ]
        prune_checkpoints: tuple[VirtualEnvironmentCheckpointRecord, ...] = checkpoints[
            max_checkpoints:
        ]
        retained_relations: dict[tuple[str | None, str | None, str], PhysicalRelationRecord] = {}
        checkpoint: VirtualEnvironmentCheckpointRecord
        for checkpoint in retained_checkpoints:
            refs: tuple[VirtualEnvironmentCheckpointModelRefRecord, ...] = (
                backend.get_virtual_environment_checkpoint_model_refs(
                    connection=connection,
                    schema=config.schema,
                    checkpoint_id=checkpoint.checkpoint_id,
                )
            )
            ref: VirtualEnvironmentCheckpointModelRefRecord
            for ref in refs:
                relation: PhysicalRelationRecord | None = backend.get_physical_relation(
                    connection=connection,
                    schema=config.schema,
                    model_name=ref.model_name,
                    version_hash=ref.version_hash,
                )
                if relation is None:
                    continue
                retained_relations[
                    (relation.database_name, relation.schema_name, relation.relation_name)
                ] = relation
        return CheckpointRetentionInspection(
            prune_checkpoints=prune_checkpoints,
            retained_physical_relations=tuple(
                retained_relations[key] for key in sorted(retained_relations)
            ),
        )
    finally:
        backend.close(connection)
