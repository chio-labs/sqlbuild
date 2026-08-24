"""Public virtual microbatch replay retention inspection helper."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.microbatches.models import MicrobatchEvent
from sqlbuild.virtual.state._helpers.state_lifecycle.microbatch_replay_retention import (
    active_microbatch_replay_roots,
)
from sqlbuild.virtual.state._helpers.state_runtime.runtime import build_state_runtime
from sqlbuild.virtual.state.models import (
    PhysicalRelationRecord,
    StateLockRecord,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentRetentionRecord,
)


def inspect_active_microbatch_replay_relations(
    *, project_dir: Path, discovered_inputs: DiscoveredProjectInputs
) -> tuple[PhysicalRelationRecord, ...]:
    """Resolve incomplete replay requirements to tracked physical relations."""

    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    connection: Any = backend.connect(config.connection)
    try:
        events: tuple[MicrobatchEvent, ...] = backend.read_microbatch_retention_history(
            connection=connection,
            schema=config.schema,
        )
        current_versions: dict[str, set[str]] = {}
        environments: tuple[VirtualEnvironmentRetentionRecord, ...] = (
            backend.list_virtual_environments(connection=connection, schema=config.schema)
        )
        for environment in environments:
            refs: tuple[VirtualEnvironmentModelRefRecord, ...] = (
                backend.get_virtual_environment_model_refs(
                    connection=connection,
                    schema=config.schema,
                    virtual_environment_name=environment.virtual_environment_name,
                )
            )
            for ref in refs:
                current_versions.setdefault(ref.model_name, set()).add(ref.version_hash)
        relations: dict[tuple[str | None, str, str], PhysicalRelationRecord] = {}
        for root in active_microbatch_replay_roots(events=events):
            model_current_versions: set[str] = current_versions.get(root.model_name, set())
            if model_current_versions and model_current_versions.isdisjoint(
                {root.version_hash, root.previous_version_hash}
            ):
                continue
            relation: PhysicalRelationRecord | None = backend.get_physical_relation(
                connection=connection,
                schema=config.schema,
                model_name=root.model_name,
                version_hash=root.version_hash,
            )
            if relation is not None:
                relations[
                    (relation.database_name, relation.schema_name, relation.relation_name)
                ] = relation
        locks: tuple[StateLockRecord, ...] = backend.list_active_locks(
            connection=connection,
            schema=config.schema,
        )
        for lock in locks:
            parsed: tuple[str, str] | None = _model_version_lock_identity(lock_key=lock.lock_key)
            if parsed is None:
                continue
            model_name, version_hash = parsed
            relation = backend.get_physical_relation(
                connection=connection,
                schema=config.schema,
                model_name=model_name,
                version_hash=version_hash,
            )
            if relation is not None:
                relations[
                    (relation.database_name, relation.schema_name, relation.relation_name)
                ] = relation
        return tuple(relations[key] for key in sorted(relations))
    finally:
        backend.close(connection)


def _model_version_lock_identity(*, lock_key: str) -> tuple[str, str] | None:
    prefix: str = "model_version:"
    if not lock_key.startswith(prefix):
        return None
    model_identity, separator, version_hash = lock_key.removeprefix(prefix).rpartition(":")
    if not separator:
        return None
    _warehouse_realm, realm_separator, model_name = model_identity.partition(":")
    return (model_name if realm_separator else model_identity, version_hash)
