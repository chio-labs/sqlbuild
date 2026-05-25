"""State backend config resolution helpers."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.models.environments import (
    resolve_environment_config,
    resolve_environment_name,
)
from sqlbuild.spec.models.project import EnvironmentConfig
from sqlbuild.versioned.state.exceptions import StateBackendConfigError
from sqlbuild.versioned.state.models import StateBackendConfig
from sqlbuild.versioned.state.types import StateBackendName


def resolve_state_backend_config(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    project_dir: Path,
) -> StateBackendConfig:
    """Resolve state backend config from the active physical environment."""

    environment_name: str | None = resolve_environment_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_environment=None,
    )
    if environment_name is None:
        raise StateBackendConfigError(
            "State commands require an active environment with [environments.<name>.state]"
        )
    environment_config: EnvironmentConfig = resolve_environment_config(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        environment_name=environment_name,
    )
    backend_name: str | None = environment_config.state.backend
    if backend_name is None:
        raise StateBackendConfigError(
            f"Environment '{environment_name}' does not configure a state backend"
        )
    schema: str | None = environment_config.state.schema
    if schema is None:
        raise StateBackendConfigError(
            f"Environment '{environment_name}' state config must define schema"
        )
    try:
        backend: StateBackendName = StateBackendName(backend_name)
    except ValueError as error:
        raise StateBackendConfigError(f"Unsupported state backend: {backend_name}") from error
    connection: dict[str, object] = _resolve_connection_config(
        raw_config=environment_config.state.connection,
        project_dir=project_dir,
        backend=backend,
    )
    return StateBackendConfig(
        backend=backend,
        schema=schema,
        connection=connection,
        allow_reset=environment_config.state.allow_reset,
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
