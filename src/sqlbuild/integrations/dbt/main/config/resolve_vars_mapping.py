"""Resolve dbt variables."""

from sqlbuild.integrations.dbt.helpers.planning.runtime import resolve_dbt_vars_mapping as _resolve
from sqlbuild.spec.contracts.models import DbtConfig, LocalDbtConfig


def resolve_dbt_vars_mapping(
    *, project_config: DbtConfig, local_config: LocalDbtConfig, dbt_args: tuple[str, ...]
) -> dict[str, object]:
    """Resolve merged dbt variables as a mapping."""

    return _resolve(project_config=project_config, local_config=local_config, dbt_args=dbt_args)
