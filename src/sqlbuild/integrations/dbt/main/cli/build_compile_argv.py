"""Build dbt compile arguments."""

from sqlbuild.integrations.dbt.helpers.cli.runner import build_dbt_compile_argv as _build
from sqlbuild.integrations.dbt.models import DbtCliOptions


def build_dbt_compile_argv(
    *, dbt_executable: str, options: DbtCliOptions, full_refresh: bool = False
) -> tuple[str, ...]:
    """Build argv for dbt compile."""

    return _build(dbt_executable=dbt_executable, options=options, full_refresh=full_refresh)
