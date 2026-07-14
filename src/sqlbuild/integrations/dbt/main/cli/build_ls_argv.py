"""Build dbt ls arguments."""

from collections.abc import Sequence

from sqlbuild.integrations.dbt._helpers.cli.runner import build_dbt_ls_argv as _build
from sqlbuild.integrations.dbt.models import DbtCliOptions


def build_dbt_ls_argv(
    *,
    dbt_executable: str,
    options: DbtCliOptions,
    select: Sequence[str] = (),
    exclude: Sequence[str] = (),
    resource_types: Sequence[str] = (),
) -> tuple[str, ...]:
    """Build argv for dbt ls with JSON output."""

    return _build(
        dbt_executable=dbt_executable,
        options=options,
        select=select,
        exclude=exclude,
        resource_types=resource_types,
    )
