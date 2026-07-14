"""Public effective scenario configuration resolution operation."""

from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig, ScenarioConfig
from sqlbuild.spec.resolution.helpers.project_config import (
    resolve_effective_scenario_config as _resolve_effective_scenario_config,
)


def resolve_effective_scenario_config(
    *, project_config: ProjectConfig, local_config: LocalConfig
) -> ScenarioConfig:
    """Resolve scenario config, allowing local overrides to replace project rules."""

    return _resolve_effective_scenario_config(
        project_config=project_config,
        local_config=local_config,
    )
