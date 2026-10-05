"""Active command warehouse scope for CLI warehouse connections."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

from sqlbuild.cli.commands.constants import COMMAND_WAREHOUSE_GROUPS
from sqlbuild.cli.commands.types import CliCommand
from sqlbuild.cli.entry.models import CommandWarehouseScope

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
