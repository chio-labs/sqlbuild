"""State lifecycle command entrypoint."""

from __future__ import annotations

import importlib.metadata
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.shared.helpers.cli_style import CliStyle
from sqlbuild.shared.helpers.colors import supports_color
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
    on_connection_start: Callable[[int], None] | None = None,
    on_connection_complete: Callable[[int, float], None] | None = None,
    on_connection_error: Callable[[int, float], None] | None = None,
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
            on_connection_error(1, time.perf_counter() - started_at)
        raise
    if on_connection_complete is not None:
        on_connection_complete(1, time.perf_counter() - started_at)
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
                    "state reset is disabled for this environment. To allow it, set "
                    "`allow_reset = true` under `[targets.<name>.state]` in "
                    "sqlbuild_project.toml or sqlbuild_local.toml, then rerun with "
                    "--auto-approve."
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
    style: CliStyle = CliStyle(use_color=use_color)
    rendered_title: str = style.success_strong(title)
    state_label: str = style.success("State store:")
    tables_label: str = style.success("Tables:")
    lines: list[str] = ["", rendered_title, "", state_label]
    lines.append(_summary_row(label="backend", value=config.backend.value, use_color=use_color))
    lines.append(_summary_row(label="schema", value=config.schema, use_color=use_color))
    database: object | None = config.connection.get("database")
    if database is not None:
        lines.append(_summary_row(label="database", value=str(database), use_color=use_color))
    if backup_id is not None:
        lines.append(_summary_row(label="backup", value=backup_id, use_color=use_color))
    lines.append("")
    lines.append(tables_label)
    lines.append(
        _summary_row(
            label="created/validated",
            value=str(len(STATE_TABLE_COLUMNS)),
            use_color=use_color,
        )
    )
    lines.append(
        _summary_row(
            label="current state",
            value=(
                "model_versions, function_versions, physical_relations, "
                "physical_relation_ancestry, virtual_environments, virtual_environment_refs, "
                "virtual_environment_function_refs, locks"
            ),
            use_color=use_color,
            emphasize_value=False,
        )
    )
    lines.append(
        _summary_row(
            label="history",
            value=(
                "virtual_environment_checkpoints, virtual_environment_checkpoint_refs, "
                "virtual_environment_checkpoint_function_refs, plan_runs, "
                "virtual_environment_ref_events, reconcile_events, state_migration_events"
            ),
            use_color=use_color,
            emphasize_value=False,
        )
    )
    lines.append("")
    return "\n".join(lines)


def _summary_row(*, label: str, value: str, use_color: bool, emphasize_value: bool = True) -> str:
    style: CliStyle = CliStyle(use_color=use_color)
    rendered_label: str = style.muted(f"{label}:")
    rendered_value: str = style.object_name(value) if emphasize_value else value
    return f"  {rendered_label:<24} {rendered_value}"
