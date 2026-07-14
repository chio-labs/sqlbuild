"""Parse dbt execution arguments."""

from collections.abc import Sequence

from sqlbuild.integrations.dbt._helpers.cli.arg_parser import parse_dbt_execution_args as _parse
from sqlbuild.integrations.dbt.models import DbtInteropParsedArgs
from sqlbuild.integrations.dbt.types import DbtInteropCommand


def parse_dbt_execution_args(
    *, command: DbtInteropCommand, args: Sequence[str]
) -> DbtInteropParsedArgs:
    """Parse declared dbt interop execution arguments."""

    return _parse(command=command, args=args)
