"""State lifecycle command entrypoint."""

from __future__ import annotations

import importlib.metadata
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.presentation.main.supports_color import supports_color
from sqlbuild.runtime.contracts.types import ConnectionElapsedCallback
from sqlbuild.virtual.state._helpers.state_lifecycle.lifecycle_output import (
    format_state_lifecycle_summary,
)
from sqlbuild.virtual.state._helpers.state_runtime.backend import build_state_backend
from sqlbuild.virtual.state._helpers.state_runtime.config import resolve_state_backend_config
from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.exceptions import StateBackendConfigError
from sqlbuild.virtual.state.models import StateBackendConfig, StateSchemaValidationResult
from sqlbuild.virtual.state.types import StateCommand


def run_state_lifecycle(
    *,
    project_dir: Path | None,
    command: StateCommand,
    backup_id: str | None = None,
    auto_approve: bool = False,
    no_color: bool = False,
    on_connection_start: Callable[[int], None] | None = None,
    on_connection_complete: ConnectionElapsedCallback | None = None,
    on_connection_error: ConnectionElapsedCallback | None = None,
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
    use_color: bool = not no_color and supports_color()
    backend: StateBackend = build_state_backend(config.backend)
    started_at: float = time.perf_counter()
    if on_connection_start is not None:
        on_connection_start(1)
    try:
        connection: Any = backend.connect(config.connection)
    except BaseException:
        if on_connection_error is not None:
            on_connection_error(1, elapsed_seconds=time.perf_counter() - started_at)
        raise
    if on_connection_complete is not None:
        on_connection_complete(1, elapsed_seconds=time.perf_counter() - started_at)
    try:
        return _execute_state_command(
            backend=backend,
            connection=connection,
            config=config,
            command=command,
            backup_id=backup_id,
            auto_approve=auto_approve,
            use_color=use_color,
        )
    finally:
        backend.close(connection)


def _execute_state_command(
    *,
    backend: StateBackend,
    connection: Any,
    config: StateBackendConfig,
    command: StateCommand,
    backup_id: str | None,
    auto_approve: bool,
    use_color: bool,
) -> int:
    """Run one lifecycle command against the open state backend connection."""

    if command == StateCommand.INIT:
        backend.initialize(
            connection=connection,
            schema=config.schema,
            sqlbuild_version=importlib.metadata.version("sqlbuild"),
        )
        print(
            format_state_lifecycle_summary(
                title="Virtual State Initialized",
                config=config,
                use_color=use_color,
            )
        )
        return 0
    if command == StateCommand.MIGRATE:
        created_backup_id: str = backend.create_backup(connection=connection, schema=config.schema)
        backend.initialize(
            connection=connection,
            schema=config.schema,
            sqlbuild_version=importlib.metadata.version("sqlbuild"),
        )
        print(
            format_state_lifecycle_summary(
                title="Virtual State Migrated",
                config=config,
                use_color=use_color,
                backup_id=created_backup_id,
            )
        )
        return 0
    if command == StateCommand.ROLLBACK:
        used_backup_id: str = backend.rollback(
            connection=connection,
            schema=config.schema,
            backup_id=backup_id,
        )
        print(
            format_state_lifecycle_summary(
                title="Virtual State Rolled Back",
                config=config,
                use_color=use_color,
                backup_id=used_backup_id,
            )
        )
        return 0
    if command == StateCommand.RESET:
        if not config.allow_reset:
            raise StateBackendConfigError(
                "state reset is disabled for this target. To allow it, set "
                "`allow_reset = true` under `[targets.<name>.state]` in "
                "sqlbuild_project.toml or sqlbuild_local.toml, then rerun with "
                "--auto-approve."
            )
        if not auto_approve:
            raise StateBackendConfigError("state reset requires --auto-approve")
        backend.reset(connection=connection, schema=config.schema)
        print(
            format_state_lifecycle_summary(
                title="Virtual State Reset",
                config=config,
                use_color=use_color,
            )
        )
        return 0
    validation: StateSchemaValidationResult = backend.inspect_schema(
        connection=connection,
        schema=config.schema,
    )
    print(f"State schema valid: {validation.valid}")
    return 0
