"""Command-group warehouse selection for CLI warehouse connections."""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from pathlib import Path

from sqlbuild.adapter.discovery.main.session_warehouse_support import (
    adapter_supports_session_warehouse,
)
from sqlbuild.cli.commands.constants import (
    CLI_WAREHOUSE_SOURCE,
    COMMAND_WAREHOUSE_GROUPS,
    CONNECTION_DEFAULT_WAREHOUSE_SOURCE,
    CONNECTION_WAREHOUSE_SOURCE,
)
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cli.commands.types import CliCommand
from sqlbuild.cli.entry.models import (
    AuthoredTargetWarehouse,
    CommandWarehouseScope,
    ResolvedWarehouse,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.main.effective_runtime import build_effective_runtime_config
from sqlbuild.compiler.compile.main.expand_template_data import expand_template_data
from sqlbuild.compiler.discovery.constants import LOCAL_CONFIG_FILENAME, PROJECT_CONFIG_FILENAME
from sqlbuild.compiler.discovery.main.discover_configuration import (
    discover_project_configuration,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.errors.setting_help.main.setting_help import setting_help
from sqlbuild.spec.contracts.constants import CONNECTION_WAREHOUSE_KEY
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)
from sqlbuild.spec.contracts.main.resolve_target_name import resolve_target_name
from sqlbuild.spec.contracts.models import LocalTargetConfig, TargetConfig
from sqlbuild.spec.contracts.types import WarehouseGroup

_SNOWFLAKE_IDENTIFIER_PATTERN: re.Pattern[str] = re.compile(
    r'[A-Za-z_][A-Za-z0-9_$]*|"(?:[^"]|"")+"'
)
_CONNECTION_SOURCES: frozenset[str] = frozenset(
    {CONNECTION_WAREHOUSE_SOURCE, CONNECTION_DEFAULT_WAREHOUSE_SOURCE}
)
_CURRENT_SCOPE: ContextVar[CommandWarehouseScope | None] = ContextVar(
    "sqlbuild_command_warehouse_scope", default=None
)


@contextmanager
def command_warehouse_scope(
    *,
    command: CliCommand | str | None,
    cli_warehouse: str | None,
    cli_vars: dict[str, object] | None = None,
) -> Iterator[CommandWarehouseScope]:
    """Install the warehouse group, CLI override, and CLI vars for one command invocation."""

    scope: CommandWarehouseScope = CommandWarehouseScope(
        group=None if command is None else COMMAND_WAREHOUSE_GROUPS.get(CliCommand(command)),
        cli_warehouse=cli_warehouse,
        cli_vars={} if cli_vars is None else dict(cli_vars),
    )
    token: Token[CommandWarehouseScope | None] = _CURRENT_SCOPE.set(scope)
    try:
        yield scope
    finally:
        _CURRENT_SCOPE.reset(token)


def current_command_warehouse_scope() -> CommandWarehouseScope:
    """Return the active command's warehouse scope, or an empty one outside the CLI."""

    scope: CommandWarehouseScope | None = _CURRENT_SCOPE.get()
    return scope if scope is not None else CommandWarehouseScope(group=None)


def validate_cli_warehouse(*, cli_warehouse: str | None, project_dir: Path) -> None:
    """Reject an empty, malformed, or unsupported `--warehouse` before the command runs."""

    if cli_warehouse is None:
        return
    _validate_cli_warehouse_identifier(cli_warehouse)
    discovered: DiscoveredProjectInputs = discover_project_configuration(project_dir=project_dir)
    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered.project_config, local_config=discovered.local_config
    )
    if not adapter_supports_session_warehouse(adapter_name=adapter_name, project_dir=project_dir):
        _raise_unsupported_cli_warehouse(cli_warehouse=cli_warehouse, adapter_name=adapter_name)


def find_target_group_warehouse(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    selected_target: str | None,
    group: WarehouseGroup,
) -> AuthoredTargetWarehouse | None:
    """Find the active target's authored, unexpanded warehouse for one command group."""

    target_name: str | None = resolve_target_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_target=selected_target,
    )
    if target_name is None:
        return None
    local_target: LocalTargetConfig | None = discovered_inputs.local_config.targets.get(target_name)
    project_target: TargetConfig | None = discovered_inputs.project_config.targets.get(target_name)
    local_value: str | None = (
        None if local_target is None else local_target.warehouses.for_group(group)
    )
    project_value: str | None = (
        None if project_target is None else project_target.warehouses.for_group(group)
    )
    authored: str | None = local_value if local_value is not None else project_value
    if authored is None:
        return None
    return AuthoredTargetWarehouse(
        warehouse=authored,
        target_name=target_name,
        group=group,
        file_name=LOCAL_CONFIG_FILENAME if local_value is not None else PROJECT_CONFIG_FILENAME,
    )


def resolve_command_warehouse(
    *,
    discovered_inputs: DiscoveredProjectInputs | None,
    selected_target: str | None,
    group: WarehouseGroup | None,
    cli_warehouse: str | None,
    connection_config: dict[str, object],
    cli_vars: dict[str, object] | None = None,
) -> ResolvedWarehouse:
    """Resolve one group's warehouse: CLI, then target group, then connection, then default."""

    if cli_warehouse is not None:
        _validate_cli_warehouse_identifier(cli_warehouse)
        return ResolvedWarehouse(warehouse=cli_warehouse, source=CLI_WAREHOUSE_SOURCE)
    authored: AuthoredTargetWarehouse | None = (
        None
        if group is None or discovered_inputs is None
        else find_target_group_warehouse(
            discovered_inputs=discovered_inputs, selected_target=selected_target, group=group
        )
    )
    if authored is not None and discovered_inputs is not None:
        return _expand_target_group_warehouse(
            authored=authored,
            discovered_inputs=discovered_inputs,
            selected_target=selected_target,
            cli_vars=cli_vars,
        )
    connection_warehouse: object | None = connection_config.get(CONNECTION_WAREHOUSE_KEY)
    if isinstance(connection_warehouse, str) and connection_warehouse.strip():
        return ResolvedWarehouse(warehouse=connection_warehouse, source=CONNECTION_WAREHOUSE_SOURCE)
    return ResolvedWarehouse(warehouse=None, source=CONNECTION_DEFAULT_WAREHOUSE_SOURCE)


def apply_command_warehouse(
    *,
    config: dict[str, object],
    adapter_name: str,
    project_dir: Path | None,
    discovered_inputs: DiscoveredProjectInputs | None,
    selected_target: str | None,
) -> dict[str, object]:
    """Return connection config whose warehouse follows the active command's group."""

    scope: CommandWarehouseScope = current_command_warehouse_scope()
    authored: AuthoredTargetWarehouse | None = (
        None
        if scope.group is None or discovered_inputs is None
        else find_target_group_warehouse(
            discovered_inputs=discovered_inputs,
            selected_target=selected_target,
            group=scope.group,
        )
    )
    if scope.cli_warehouse is None and authored is None:
        return config
    if not adapter_supports_session_warehouse(adapter_name=adapter_name, project_dir=project_dir):
        if scope.cli_warehouse is not None:
            _raise_unsupported_cli_warehouse(
                cli_warehouse=scope.cli_warehouse, adapter_name=adapter_name
            )
        return config
    resolved: ResolvedWarehouse = resolve_command_warehouse(
        discovered_inputs=discovered_inputs,
        selected_target=selected_target,
        group=scope.group,
        cli_warehouse=scope.cli_warehouse,
        connection_config=config,
        cli_vars=scope.cli_vars,
    )
    if resolved.source in _CONNECTION_SOURCES:
        return config
    return {**config, CONNECTION_WAREHOUSE_KEY: resolved.warehouse}


def describe_connection_warehouse(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    selected_target: str | None,
    connection_config: dict[str, object],
) -> ResolvedWarehouse:
    """Describe the warehouse an already resolved connection uses and where it came from."""

    scope: CommandWarehouseScope = current_command_warehouse_scope()
    connection_warehouse: object | None = connection_config.get(CONNECTION_WAREHOUSE_KEY)
    if not isinstance(connection_warehouse, str) or not connection_warehouse.strip():
        return ResolvedWarehouse(warehouse=None, source=CONNECTION_DEFAULT_WAREHOUSE_SOURCE)
    if scope.cli_warehouse == connection_warehouse:
        return ResolvedWarehouse(warehouse=connection_warehouse, source=CLI_WAREHOUSE_SOURCE)
    authored: AuthoredTargetWarehouse | None = (
        None
        if scope.group is None
        else find_target_group_warehouse(
            discovered_inputs=discovered_inputs,
            selected_target=selected_target,
            group=scope.group,
        )
    )
    if authored is not None and _expands_to(
        authored=authored,
        warehouse=connection_warehouse,
        discovered_inputs=discovered_inputs,
        selected_target=selected_target,
        cli_vars=scope.cli_vars,
    ):
        return ResolvedWarehouse(warehouse=connection_warehouse, source=authored.source)
    return ResolvedWarehouse(warehouse=connection_warehouse, source=CONNECTION_WAREHOUSE_SOURCE)


def _expands_to(
    *,
    authored: AuthoredTargetWarehouse,
    warehouse: str,
    discovered_inputs: DiscoveredProjectInputs,
    selected_target: str | None,
    cli_vars: dict[str, object],
) -> bool:
    try:
        resolved: ResolvedWarehouse = _expand_target_group_warehouse(
            authored=authored,
            discovered_inputs=discovered_inputs,
            selected_target=selected_target,
            cli_vars=cli_vars,
        )
    except (CompileInputError, CliUserError):
        return False
    return resolved.warehouse == warehouse


def _expand_target_group_warehouse(
    *,
    authored: AuthoredTargetWarehouse,
    discovered_inputs: DiscoveredProjectInputs,
    selected_target: str | None,
    cli_vars: dict[str, object] | None,
) -> ResolvedWarehouse:
    effective_vars: dict[str, object] = build_effective_runtime_config(
        discovered_inputs=discovered_inputs,
        selected_target=selected_target,
        cli_vars=cli_vars,
    )[1]
    warehouse: str = str(
        expand_template_data(
            value=authored.warehouse,
            variables=effective_vars,
            context_values={},
            context_label=f"targets.{authored.target_name}.warehouses.{authored.group.value}",
            allow_context=False,
            preserve_context_tokens=False,
            preserve_unknown_context=False,
        )
    )
    if _SNOWFLAKE_IDENTIFIER_PATTERN.fullmatch(warehouse) is None:
        section: str = f"targets.{authored.target_name}.warehouses"
        raise CliUserError(
            f"{authored.file_name} [{section}] {authored.group.value} resolves to "
            f"{warehouse!r}, which is not a valid Snowflake warehouse identifier",
            code="C261",
            help=setting_help(
                purpose='to use an unquoted identifier (or a double-quoted one such as "Adhoc WH")',
                file_name=authored.file_name,
                section=section,
                key=authored.group.value,
                value="ADHOC_WH",
            ),
        )
    return ResolvedWarehouse(warehouse=warehouse, source=authored.source)


def _validate_cli_warehouse_identifier(cli_warehouse: str) -> None:
    if not cli_warehouse.strip():
        raise CliUserError(
            "--warehouse requires a warehouse name",
            code="C261",
            help="pass a name such as `--warehouse ADHOC_WH`, or omit the flag",
        )
    if _SNOWFLAKE_IDENTIFIER_PATTERN.fullmatch(cli_warehouse) is None:
        raise CliUserError(
            f"--warehouse {cli_warehouse!r} is not a valid Snowflake warehouse identifier",
            code="C261",
            help=(
                "pass an unquoted identifier such as `--warehouse ADHOC_WH`, or a double-quoted "
                """identifier such as `--warehouse '"Adhoc WH"'`"""
            ),
        )


def _raise_unsupported_cli_warehouse(*, cli_warehouse: str, adapter_name: str) -> None:
    raise CliUserError(
        f"--warehouse {cli_warehouse} was given, but the '{adapter_name}' adapter has no "
        "warehouse to select",
        code="C260",
        help=(
            "remove --warehouse; it needs an adapter with a session warehouse, such as "
            "snowflake or an adapter extending it"
        ),
    )
