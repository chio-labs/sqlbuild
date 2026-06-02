"""State backend config resolution helpers."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.models.project import TargetConfig
from sqlbuild.spec.models.targets import (
    resolve_target_config,
    resolve_target_name,
)
from sqlbuild.virtual.state.exceptions import StateBackendConfigError
from sqlbuild.virtual.state.models import StateBackendConfig
from sqlbuild.virtual.state.types import StateBackendName


def resolve_state_backend_config(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    project_dir: Path,
) -> StateBackendConfig:
    """Resolve state backend config from the active physical environment."""

    if not discovered_inputs.project_config.settings.virtual_environments:
        raise StateBackendConfigError("State commands require virtual_environments = true")

    target_name: str | None = resolve_target_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_target=None,
    )
    if target_name is None:
        raise StateBackendConfigError(
            "State commands require an active target with [targets.<name>.state]"
        )
    target_config: TargetConfig = resolve_target_config(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        target_name=target_name,
    )
    backend_name: str | None = target_config.state.backend
    if backend_name is None:
        raise StateBackendConfigError(f"Target '{target_name}' does not configure a state backend")
    schema: str | None = target_config.state.schema
    if schema is None:
        raise StateBackendConfigError(f"Target '{target_name}' state config must define schema")
    try:
        backend: StateBackendName = StateBackendName(backend_name)
    except ValueError as error:
        raise StateBackendConfigError(f"Unsupported state backend: {backend_name}") from error
    connection: dict[str, object] = _resolve_connection_config(
        raw_config=target_config.state.connection,
        project_dir=project_dir,
        backend=backend,
    )
    return StateBackendConfig(
        backend=backend,
        schema=schema,
        connection=connection,
        allow_reset=target_config.state.allow_reset,
    )


def _resolve_connection_config(
    *, raw_config: dict[str, object], project_dir: Path, backend: StateBackendName
) -> dict[str, object]:
    config: dict[str, object] = dict(raw_config)
    database: object | None = config.get("database")
    if (
        backend == StateBackendName.DUCKDB
        and isinstance(database, str)
        and not Path(database).is_absolute()
        and database != ":memory:"
    ):
        config["database"] = str(project_dir / database)
    return config
