"""State lifecycle command entrypoint."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path
from typing import Any

from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.shared.helpers.colors import green, green_bold, supports_color
from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.constants import STATE_TABLE_COLUMNS
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
    no_color: bool = False,
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
    use_color: bool = not no_color and supports_color()
    try:
        if command == StateCommand.INIT:
            backend.initialize(
                connection,
                schema=config.schema,
                sqlbuild_version=importlib.metadata.version("sqlbuild"),
            )
            print(
                _format_state_lifecycle_summary(
                    title="Virtual State Initialized",
                    config=config,
                    use_color=use_color,
                )
            )
            return 0
        if command == StateCommand.MIGRATE:
            created_backup_id: str = backend.create_backup(connection, schema=config.schema)
            backend.initialize(
                connection,
                schema=config.schema,
                sqlbuild_version=importlib.metadata.version("sqlbuild"),
            )
            print(
                _format_state_lifecycle_summary(
                    title="Virtual State Migrated",
                    config=config,
                    use_color=use_color,
                    backup_id=created_backup_id,
                )
            )
            return 0
        if command == StateCommand.ROLLBACK:
            used_backup_id: str = backend.rollback(
                connection,
                schema=config.schema,
                backup_id=backup_id,
            )
            print(
                _format_state_lifecycle_summary(
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
                    "state reset requires environments.<name>.state.allow_reset = true"
                )
            if not auto_approve:
                raise StateBackendConfigError("state reset requires --auto-approve")
            backend.reset(connection, schema=config.schema)
            print(
                _format_state_lifecycle_summary(
                    title="Virtual State Reset",
                    config=config,
                    use_color=use_color,
                )
            )
            return 0
        validation: StateSchemaValidationResult = backend.validate_schema(
            connection,
            schema=config.schema,
        )
        print(f"State schema valid: {validation.valid}")
        return 0
    finally:
        backend.close(connection)


def _format_state_lifecycle_summary(
    *,
    title: str,
    config: StateBackendConfig,
    use_color: bool,
    backup_id: str | None = None,
) -> str:
    rendered_title: str = green_bold(title) if use_color else title
    state_label: str = green("State store:") if use_color else "State store:"
    tables_label: str = green("Tables:") if use_color else "Tables:"
    lines: list[str] = ["", rendered_title, "", state_label]
    lines.append(f"  backend: {config.backend.value}")
    lines.append(f"  schema: {config.schema}")
    database: object | None = config.connection.get("database")
    if database is not None:
        lines.append(f"  database: {database}")
    if backup_id is not None:
        lines.append(f"  backup: {backup_id}")
    lines.append("")
    lines.append(tables_label)
    lines.append(f"  created/validated: {len(STATE_TABLE_COLUMNS)}")
    lines.append(
        "  current state: model_versions, physical_relations, "
        "virtual_environments, virtual_environment_refs, locks"
    )
    lines.append(
        "  history: plan_runs, virtual_environment_ref_events, "
        "reconcile_events, state_migration_events"
    )
    lines.append("")
    return "\n".join(lines)
