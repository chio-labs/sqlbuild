"""Thin entry to validate `sqb dbt` execution-command arguments early."""

from __future__ import annotations

from collections.abc import Sequence

from sqlbuild.integrations.dbt.constants import (
    DBT_EXECUTION_COMMANDS,
    DBT_EXECUTION_DISPLAY_FLAGS,
)
from sqlbuild.integrations.dbt.helpers.cli.arg_parser import parse_dbt_execution_args
from sqlbuild.integrations.dbt.types import DbtInteropCommand


def validate_dbt_execution_args(*, command: DbtInteropCommand, args: Sequence[str]) -> None:
    """Parse execution-command args early so `-h` and typos resolve before setup."""

    if command not in DBT_EXECUTION_COMMANDS:
        return
    display_free_args: tuple[str, ...] = tuple(
        arg for arg in args if arg not in DBT_EXECUTION_DISPLAY_FLAGS
    )
    _ = parse_dbt_execution_args(command=command, args=display_free_args)
