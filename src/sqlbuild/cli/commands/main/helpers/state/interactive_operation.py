"""Shared CLI setup for interactive state operations."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_project_connection_config
from sqlbuild.cli.commands.main.shared.helpers.connection_progress import ConnectionProgressReporter
from sqlbuild.cli.commands.main.shared.helpers.status import TransientStatusReporter
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.shared.helpers.colors import supports_color
from sqlbuild.spec.models.project import EnvironmentConfig, resolve_effective_adapter_name
from sqlbuild.virtual.state.main.runtime import build_state_runtime
from sqlbuild.virtual.state.types import StateCommand


def run_interactive_state_operation(
    *,
    project_dir: Path | None,
    state_command: StateCommand,
    operation_runner: Callable[..., str],
    auto_approve: bool,
    allow_copy: bool,
    no_color: bool = False,
) -> int:
    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    environment_name: str | None = (
        discovered_inputs.local_config.environment
        or discovered_inputs.project_config.default_environment
    )
    if environment_name is None:
        raise CliUserError(
            f"state {state_command.value} requires an active environment",
            code="C255",
        )
    effective_environment: EnvironmentConfig | None = (
        discovered_inputs.project_config.environments.get(environment_name)
    )
    if (
        effective_environment is None
        or effective_environment.state.unsuffixed_virtual_env != environment_name
    ):
        raise CliUserError(
            (
                f"state {state_command.value} requires "
                f"[environments.{environment_name}.state] unsuffixed_virtual_env = "
                f"'{environment_name}'"
            ),
            code="C256",
        )
    if auto_approve:
        raise CliUserError(
            (
                f"state {state_command.value} is interactive-only and does not support "
                "--auto-approve"
            ),
            code="C257",
        )
    prompt: str = f"Type '{state_command.value} {environment_name}' to confirm: "
    if input(prompt).strip() != f"{state_command.value} {environment_name}":
        raise CliUserError(f"state {state_command.value} cancelled", code="C258")
    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(adapter_name, project_dir=effective_project_dir)
    connection_config: dict[str, object] = resolve_project_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=effective_project_dir,
    )
    use_color: bool = not no_color and supports_color()
    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs,
        project_dir=effective_project_dir,
    )
    state_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=f"{config.backend.value} state store",
        stream=sys.stdout,
        use_color=use_color,
    )
    state_started_at: float = time.perf_counter()
    state_progress.on_connection_start(1)
    try:
        state_connection: Any = backend.connect(config.connection)
    except BaseException:
        state_progress.on_connection_error(1, time.perf_counter() - state_started_at)
        raise
    state_progress.on_connection_complete(1, time.perf_counter() - state_started_at)
    warehouse_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        stream=sys.stdout,
        use_color=use_color,
    )
    warehouse_started_at: float = time.perf_counter()
    warehouse_progress.on_connection_start(1)
    try:
        warehouse_connection: Any = adapter.connect(connection_config)
    except BaseException:
        warehouse_progress.on_connection_error(1, time.perf_counter() - warehouse_started_at)
        backend.close(state_connection)
        raise
    warehouse_progress.on_connection_complete(1, time.perf_counter() - warehouse_started_at)
    status: TransientStatusReporter = TransientStatusReporter(
        stream=sys.stdout,
        use_color=use_color,
    )
    try:
        status.start(f"Running state {state_command.value}...")
        message: str = operation_runner(
            discovered_inputs=discovered_inputs,
            config=config,
            backend=backend,
            state_connection=state_connection,
            adapter=adapter,
            connection=warehouse_connection,
            allow_copy=allow_copy,
        )
        status.complete(f"State {state_command.value} complete.")
    finally:
        status.close()
        adapter.close(warehouse_connection)
        backend.close(state_connection)
    print(message)
    return 0
