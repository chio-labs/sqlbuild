"""Route dbt interop arguments."""

from sqlbuild.integrations.dbt.helpers.cli.args import route_dbt_interop_args as _route
from sqlbuild.integrations.dbt.models import DbtInteropParsedArgs, DbtInteropRoutedArgs
from sqlbuild.integrations.dbt.types import DbtInteropCommand


def route_dbt_interop_args(
    *, command: DbtInteropCommand | str, parsed: DbtInteropParsedArgs
) -> DbtInteropRoutedArgs:
    """Route parsed arguments to dbt and SQLBuild."""

    return _route(command=command, parsed=parsed)
