"""Parse dbt configuration overrides."""

from sqlbuild.integrations.dbt.helpers.planning.runtime import parse_dbt_config_overrides as _parse
from sqlbuild.integrations.dbt.models import DbtCliConfigOverrides


def parse_dbt_config_overrides(dbt_args: tuple[str, ...]) -> DbtCliConfigOverrides:
    """Parse dbt configuration flags."""

    return _parse(dbt_args)
