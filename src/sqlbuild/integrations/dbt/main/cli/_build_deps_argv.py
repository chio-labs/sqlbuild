"""Build dbt deps arguments."""

from sqlbuild.integrations.dbt._helpers.cli.runner import build_dbt_deps_argv as _build
from sqlbuild.integrations.dbt.models import DbtCliOptions


def build_dbt_deps_argv(*, dbt_executable: str, options: DbtCliOptions) -> tuple[str, ...]:
    """Build argv for dbt deps."""

    return _build(dbt_executable=dbt_executable, options=options)
