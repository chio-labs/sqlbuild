"""Public scenario local type override selection operation."""

from sqlbuild.spec.contracts.models import ScenarioConfig
from sqlbuild.spec.resolution.helpers.project_config import (
    scenario_local_type_overrides_for_dialect as _scenario_local_type_overrides_for_dialect,
)


def scenario_local_type_overrides_for_dialect(
    *, scenario_config: ScenarioConfig, sql_analysis_dialect: str | None
) -> dict[str, str]:
    """Return global and dialect-specific scenario local type override rules."""

    return _scenario_local_type_overrides_for_dialect(
        scenario_config=scenario_config,
        sql_analysis_dialect=sql_analysis_dialect,
    )
