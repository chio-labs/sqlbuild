"""Debug command check execution helpers."""

from __future__ import annotations

import platform
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.helpers.debug.models import DebugLine, DebugResult
from sqlbuild.cli.commands.main.helpers.debug.types import DebugCheckStatus
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_project_connection_config
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.models.project import resolve_effective_adapter_name

_SECRET_CONNECTION_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "private_key",
        "private_key_file_pwd",
        "secret",
        "token",
    }
)


def build_debug_result(*, project_dir: Path, check_connection: bool) -> DebugResult:
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    local_config_path: Path = project_dir / "sqlbuild_local.yml"
    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(adapter_name, project_dir=project_dir)
    connection_config: dict[str, object] = resolve_project_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    runtime: list[DebugLine] = _build_runtime_lines()
    configuration: list[DebugLine] = [
        DebugLine(
            label="project file",
            message=str(project_dir / "sqlbuild_project.yml"),
            status=DebugCheckStatus.OK,
            status_message="found and valid",
        ),
        DebugLine(
            label="local config",
            message=str(local_config_path) if local_config_path.exists() else "not present",
            status=DebugCheckStatus.OK,
            status_message="found" if local_config_path.exists() else "not present",
        ),
        DebugLine(
            label="project",
            message=discovered_inputs.project_config.name,
            status=DebugCheckStatus.OK,
            status_message="loaded",
        ),
        DebugLine(
            label="adapter",
            message=adapter_name,
            status=DebugCheckStatus.OK,
            status_message="found",
        ),
        DebugLine(
            label="environment",
            message=_resolve_environment_label(discovered_inputs=discovered_inputs),
            status=DebugCheckStatus.OK,
            status_message="resolved",
        ),
    ]
    connection: list[DebugLine] = _build_connection_config_lines(connection_config)
    _append_connection_checks(
        connection_lines=connection,
        adapter=adapter,
        connection_config=connection_config,
        check_connection=check_connection,
    )
    return DebugResult(
        runtime=tuple(runtime),
        configuration=tuple(configuration),
        connection=tuple(connection),
    )


def _build_runtime_lines() -> list[DebugLine]:
    try:
        sqlbuild_version: str = version("sqlbuild")
    except PackageNotFoundError:
        sqlbuild_version = "unknown"
    return [
        DebugLine(label="sqlbuild version", message=sqlbuild_version),
        DebugLine(label="python version", message=platform.python_version()),
        DebugLine(label="python path", message=sys.executable),
        DebugLine(label="os info", message=platform.platform()),
    ]


def _resolve_environment_label(*, discovered_inputs: DiscoveredProjectInputs) -> str:
    environment: str | None = discovered_inputs.local_config.environment
    if environment is not None:
        return environment
    if discovered_inputs.project_config.default_environment is not None:
        return discovered_inputs.project_config.default_environment
    return "default"


def _build_connection_config_lines(connection_config: dict[str, object]) -> list[DebugLine]:
    if not connection_config:
        return [DebugLine(label="settings", message="no keys", status=DebugCheckStatus.OK)]
    return [
        DebugLine(label=key, message=_sanitize_connection_value(key=key, value=value))
        for key, value in sorted(connection_config.items())
    ]


def _append_connection_checks(
    *,
    connection_lines: list[DebugLine],
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    check_connection: bool,
) -> None:
    if not check_connection:
        connection_lines.append(
            DebugLine(
                label="connection test",
                message="",
                status=DebugCheckStatus.SKIP,
                status_message="skipped by --no-connection",
            )
        )
        connection_lines.append(
            DebugLine(
                label="query test",
                message="",
                status=DebugCheckStatus.SKIP,
                status_message="connection skipped",
            )
        )
        return

    connection: object | None = None
    try:
        connection = adapter.connect(connection_config)
        connection_lines.append(
            DebugLine(
                label="connection test",
                message="",
                status=DebugCheckStatus.OK,
                status_message="connected",
            )
        )
    except Exception as error:
        connection_lines.append(
            DebugLine(
                label="connection test",
                message="",
                status=DebugCheckStatus.ERROR,
                status_message=str(error),
            )
        )
        connection_lines.append(
            DebugLine(
                label="query test",
                message="",
                status=DebugCheckStatus.SKIP,
                status_message="connection failed",
            )
        )
        return

    try:
        adapter.query(connection, "SELECT 1", limit=None)
        connection_lines.append(
            DebugLine(
                label="query test",
                message="",
                status=DebugCheckStatus.OK,
                status_message="SELECT 1",
            )
        )
    except Exception as error:
        connection_lines.append(
            DebugLine(
                label="query test",
                message="",
                status=DebugCheckStatus.ERROR,
                status_message=str(error),
            )
        )
    finally:
        adapter.close(connection)


def _sanitize_connection_value(*, key: str, value: object) -> str:
    if key.lower() in _SECRET_CONNECTION_KEYS:
        return "****"
    if value is None:
        return "null"
    if isinstance(value, bool | int | float):
        return str(value)
    text: str = str(value)
    if len(text) <= 32:
        return text
    return f"{text[:4]}...{text[-4:]}"
