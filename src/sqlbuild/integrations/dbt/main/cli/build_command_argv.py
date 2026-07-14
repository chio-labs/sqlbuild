"""Build dbt command arguments."""

from collections.abc import Sequence

from sqlbuild.integrations.dbt.helpers.cli.runner import build_dbt_command_argv as _build
from sqlbuild.integrations.dbt.models import DbtCliOptions


def build_dbt_command_argv(
    *,
    dbt_executable: str,
    command: str,
    options: DbtCliOptions,
    args: Sequence[str] = (),
) -> tuple[str, ...]:
    """Build argv for an executable dbt command."""

    return _build(dbt_executable=dbt_executable, command=command, options=options, args=args)
