"""Build dbt debug arguments."""

from collections.abc import Sequence

from sqlbuild.integrations.dbt.helpers.cli.runner import build_dbt_debug_argv as _build
from sqlbuild.integrations.dbt.models import DbtCliOptions


def build_dbt_debug_argv(
    *, dbt_executable: str, options: DbtCliOptions, args: Sequence[str] = ()
) -> tuple[str, ...]:
    """Build argv for dbt debug."""

    return _build(dbt_executable=dbt_executable, options=options, args=args)
