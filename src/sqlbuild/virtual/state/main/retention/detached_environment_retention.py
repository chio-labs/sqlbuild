"""Public detached VDE retention inspection helper."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.virtual.state.helpers.detached_retention import (
    build_detached_environment_inspection,
)
from sqlbuild.virtual.state.helpers.runtime import build_state_runtime
from sqlbuild.virtual.state.models import (
    DetachedVirtualEnvironmentInspection,
    PhysicalRelationRecord,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentRetentionRecord,
)


def inspect_detached_environment_retention(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    retention_days: int,
) -> DetachedVirtualEnvironmentInspection:
    """Inspect detached VDE cleanup and retained current-ref physical relations."""

    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    connection: Any = backend.connect(config.connection)
    try:
        environments: tuple[VirtualEnvironmentRetentionRecord, ...] = (
            backend.list_virtual_environments(connection=connection, schema=config.schema)
        )
        refs_by_environment: dict[str, tuple[VirtualEnvironmentModelRefRecord, ...]] = {}
        physical_relations_by_ref: dict[tuple[str, str], PhysicalRelationRecord] = {}
        environment: VirtualEnvironmentRetentionRecord
        for environment in environments:
            refs: tuple[VirtualEnvironmentModelRefRecord, ...] = (
                backend.get_virtual_environment_model_refs(
                    connection=connection,
                    schema=config.schema,
                    virtual_environment_name=environment.virtual_environment_name,
                )
            )
            refs_by_environment[environment.virtual_environment_name] = refs
            ref: VirtualEnvironmentModelRefRecord
            for ref in refs:
                relation: PhysicalRelationRecord | None = backend.get_physical_relation(
                    connection=connection,
                    schema=config.schema,
                    model_name=ref.model_name,
                    version_hash=ref.version_hash,
                )
                if relation is not None:
                    physical_relations_by_ref[(ref.model_name, ref.version_hash)] = relation
        return build_detached_environment_inspection(
            environments=environments,
            refs_by_environment=refs_by_environment,
            physical_relations_by_ref=physical_relations_by_ref,
            retention_days=retention_days,
            now=datetime.now(UTC),
        )
    finally:
        backend.close(connection)
