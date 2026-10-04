"""Debug command check execution helpers."""

from __future__ import annotations

import platform
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.runtime.adapters import resolve_adapter
from sqlbuild.cli.commands._helpers.runtime.connection import (
    resolve_project_connection_config,
)
from sqlbuild.cli.commands._helpers.runtime.warehouses import (
    apply_command_warehouse,
    command_warehouse_scope,
    current_command_warehouse_scope,
    find_target_group_warehouse,
    resolve_command_warehouse,
)
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cli.commands.models import DebugLine, DebugResult
from sqlbuild.cli.commands.types import DebugCheckStatus
from sqlbuild.cli.entry.models import (
    AuthoredTargetWarehouse,
    CommandWarehouseScope,
    ResolvedWarehouse,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.main.effective_target_namespace import (
    build_effective_target_namespace,
)
from sqlbuild.compiler.discovery.constants import (
    LEGACY_LOCAL_CONFIG_FILENAME,
    LEGACY_PROJECT_CONFIG_FILENAME,
    LOCAL_CONFIG_FILENAME,
    PROJECT_CONFIG_FILENAME,
)
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs, DiscoveredProvider
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)
from sqlbuild.spec.contracts.models import TargetConfig
from sqlbuild.spec.contracts.types import WarehouseGroup

_SECRET_CONNECTION_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "private_key",
        "private_key_file_pwd",
        "secret",
        "token",
    }
)


def build_debug_result(
    *, project_dir: Path, check_connection: bool, selected_target: str | None = None
) -> DebugResult:
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    project_config_path: Path = _resolve_existing_path(
        project_dir=project_dir,
        preferred_filename=PROJECT_CONFIG_FILENAME,
        legacy_filename=LEGACY_PROJECT_CONFIG_FILENAME,
    )
    local_config_path: Path = _resolve_existing_path(
        project_dir=project_dir,
        preferred_filename=LOCAL_CONFIG_FILENAME,
        legacy_filename=LEGACY_LOCAL_CONFIG_FILENAME,
    )
    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(adapter_name=adapter_name, project_dir=project_dir)
    command_scope: CommandWarehouseScope = current_command_warehouse_scope()
    with command_warehouse_scope(command=None, cli_warehouse=None):
        base_connection_config: dict[str, object] = resolve_project_connection_config(
            discovered_inputs=discovered_inputs,
            project_dir=project_dir,
            selected_target=selected_target,
        )
    connection_config: dict[str, object]
    try:
        connection_config = apply_command_warehouse(
            config=base_connection_config,
            adapter_name=adapter_name,
            project_dir=project_dir,
            discovered_inputs=discovered_inputs,
            selected_target=selected_target,
        )
    except (CompileInputError, CliUserError):
        connection_config = base_connection_config
    target_name: str | None
    target_config: TargetConfig | None
    target_database: str | None
    target_schema: str | None
    target_name, target_config, target_database, target_schema = build_effective_target_namespace(
        discovered_inputs=discovered_inputs,
        selected_target=selected_target,
        connection_database=connection_config.get("database"),
        connection_schema=connection_config.get("schema"),
        default_database=adapter.default_database(),
        default_schema=adapter.default_schema(),
    )
    runtime: list[DebugLine] = _build_runtime_lines()
    configuration: list[DebugLine] = [
        DebugLine(
            label="project file",
            message=str(project_config_path),
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
            label="target",
            message=target_name or "default",
            status=DebugCheckStatus.OK,
            status_message="resolved",
        ),
        DebugLine(
            label="connection",
            message=(
                target_config.connection_name
                if target_config is not None and target_config.connection_name is not None
                else "inline"
            ),
            status=DebugCheckStatus.OK,
            status_message="resolved",
        ),
        DebugLine(
            label="database",
            message=_display_target_value(target_database),
            status=DebugCheckStatus.OK,
            status_message="resolved",
        ),
        DebugLine(
            label="schema",
            message=_display_target_value(target_schema),
            status=DebugCheckStatus.OK,
            status_message="resolved",
        ),
        *_build_warehouse_lines(
            adapter=adapter,
            discovered_inputs=discovered_inputs,
            selected_target=selected_target,
            command_scope=command_scope,
            base_connection_config=base_connection_config,
        ),
    ]
    connection: list[DebugLine] = _build_connection_config_lines(connection_config)
    connection = _append_connection_checks(
        connection_lines=connection,
        adapter=adapter,
        connection_config=connection_config,
        check_connection=check_connection,
    )
    return DebugResult(
        runtime=tuple(runtime),
        configuration=tuple(configuration),
        providers=tuple(_build_provider_lines(discovered_inputs.providers)),
        connection=tuple(connection),
    )


def _build_warehouse_lines(
    *,
    adapter: BaseAdapter,
    discovered_inputs: DiscoveredProjectInputs,
    selected_target: str | None,
    command_scope: CommandWarehouseScope,
    base_connection_config: dict[str, object],
) -> list[DebugLine]:
    lines: list[DebugLine] = []
    group: WarehouseGroup
    for group in WarehouseGroup:
        authored: AuthoredTargetWarehouse | None = find_target_group_warehouse(
            discovered_inputs=discovered_inputs, selected_target=selected_target, group=group
        )
        if not adapter.supports_session_warehouse:
            if authored is not None:
                lines.append(
                    DebugLine(
                        label=f"{group.value} warehouse",
                        message=f"not used (adapter {adapter.adapter_name})",
                        status=DebugCheckStatus.SKIP,
                        status_message=authored.source,
                    )
                )
            continue
        lines.append(
            _build_warehouse_line(
                group=group,
                discovered_inputs=discovered_inputs,
                selected_target=selected_target,
                command_scope=command_scope,
                base_connection_config=base_connection_config,
            )
        )
    return lines


def _build_warehouse_line(
    *,
    group: WarehouseGroup,
    discovered_inputs: DiscoveredProjectInputs,
    selected_target: str | None,
    command_scope: CommandWarehouseScope,
    base_connection_config: dict[str, object],
) -> DebugLine:
    try:
        resolved: ResolvedWarehouse = resolve_command_warehouse(
            discovered_inputs=discovered_inputs,
            selected_target=selected_target,
            group=group,
            cli_warehouse=command_scope.cli_warehouse,
            connection_config=base_connection_config,
            cli_vars=command_scope.cli_vars,
        )
    except (CompileInputError, CliUserError) as error:
        return DebugLine(
            label=f"{group.value} warehouse",
            message=f"error: {error.message if isinstance(error, CliUserError) else error}",
            status=DebugCheckStatus.ERROR,
            status_message="unresolved",
        )
    return DebugLine(
        label=f"{group.value} warehouse",
        message=resolved.warehouse or "not set",
        status=DebugCheckStatus.OK,
        status_message=resolved.source,
    )


def _resolve_existing_path(
    *, project_dir: Path, preferred_filename: str, legacy_filename: str
) -> Path:
    preferred_path: Path = project_dir / preferred_filename
    if preferred_path.exists():
        return preferred_path
    legacy_path: Path = project_dir / legacy_filename
    if legacy_path.exists():
        return legacy_path
    return preferred_path


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


def _display_target_value(value: object | None) -> str:
    return value if isinstance(value, str) and value else "not configured"


def _build_connection_config_lines(connection_config: dict[str, object]) -> list[DebugLine]:
    if not connection_config:
        return [DebugLine(label="settings", message="no keys", status=DebugCheckStatus.OK)]
    return [
        DebugLine(label=key, message=_sanitize_connection_value(key=key, value=value))
        for key, value in sorted(connection_config.items())
    ]


def _build_provider_lines(providers: tuple[DiscoveredProvider, ...]) -> list[DebugLine]:
    if not providers:
        return [
            DebugLine(
                label="providers",
                message="none discovered",
                status=DebugCheckStatus.OK,
            )
        ]
    lines: list[DebugLine] = [
        DebugLine(
            label="providers",
            message=str(len(providers)),
            status=DebugCheckStatus.OK,
            status_message="discovered",
        )
    ]
    provider: DiscoveredProvider
    for provider in providers:
        lines.append(
            DebugLine(
                label=provider.name,
                message=f"{provider.relative_path}:{provider.provider_class.__name__}",
                status=DebugCheckStatus.OK,
                status_message="valid settings",
            )
        )
    return lines


def _append_connection_checks(
    *,
    connection_lines: list[DebugLine],
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    check_connection: bool,
) -> list[DebugLine]:
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
        return connection_lines

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
        return connection_lines

    try:
        adapter.query(connection=connection, sql="SELECT 1", limit=None)
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
    return connection_lines


def _sanitize_connection_value(*, key: str, value: object) -> str:
    if key.lower() in _SECRET_CONNECTION_KEYS:
        return "****"
    if value is None:
        return "null"
    if isinstance(value, bool | int | float):
        return str(value)
    text: str = str(value)
    digest_preview_character_limit: int = 32
    if len(text) <= digest_preview_character_limit:
        return text
    return f"{text[:4]}...{text[-4:]}"
