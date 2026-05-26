"""State lifecycle command entrypoint."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path
from typing import Any

from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.exceptions import StateBackendConfigError
from sqlbuild.virtual.state.helpers.backend import build_state_backend
from sqlbuild.virtual.state.helpers.config import resolve_state_backend_config
from sqlbuild.virtual.state.models import StateBackendConfig, StateSchemaValidationResult
from sqlbuild.virtual.state.types import StateCommand


def run_state_lifecycle(
    *,
    project_dir: Path | None,
    command: StateCommand,
    backup_id: str | None = None,
    auto_approve: bool = False,
) -> int:
    """Run a virtual state lifecycle command."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    config: StateBackendConfig = resolve_state_backend_config(
        discovered_inputs=discovered_inputs,
        project_dir=effective_project_dir,
    )
    backend: StateBackend = build_state_backend(config.backend)
    connection: Any = backend.connect(config.connection)
    try:
        if command == StateCommand.INIT:
            backend.initialize(
                connection,
                schema=config.schema,
                sqlbuild_version=importlib.metadata.version("sqlbuild"),
            )
            print(f"Initialized virtual state schema '{config.schema}'.")
            return 0
        if command == StateCommand.MIGRATE:
            created_backup_id: str = backend.create_backup(connection, schema=config.schema)
            backend.initialize(
                connection,
                schema=config.schema,
                sqlbuild_version=importlib.metadata.version("sqlbuild"),
            )
            print(
                f"Migrated virtual state schema '{config.schema}' "
                f"after backup '{created_backup_id}'."
            )
            return 0
        if command == StateCommand.ROLLBACK:
            used_backup_id: str = backend.rollback(
                connection,
                schema=config.schema,
                backup_id=backup_id,
            )
            print(f"Rolled back virtual state schema '{config.schema}' to '{used_backup_id}'.")
            return 0
        if command == StateCommand.RESET:
            if not config.allow_reset:
                raise StateBackendConfigError(
                    "state reset requires environments.<name>.state.allow_reset = true"
                )
            if not auto_approve:
                raise StateBackendConfigError("state reset requires --auto-approve")
            backend.reset(connection, schema=config.schema)
            print(f"Reset virtual state schema '{config.schema}'.")
            return 0
        validation: StateSchemaValidationResult = backend.validate_schema(
            connection,
            schema=config.schema,
        )
        print(f"State schema valid: {validation.valid}")
        return 0
    finally:
        backend.close(connection)
