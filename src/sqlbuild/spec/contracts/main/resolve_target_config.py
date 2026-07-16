"""Public target configuration resolution operation."""

from sqlbuild.spec.contracts._helpers.targets import (
    resolve_target_config as _resolve_target_config,
)
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig, TargetConfig


def resolve_target_config(
    *,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    target_name: str,
) -> TargetConfig:
    """Merge project target config with local developer overrides."""

    return _resolve_target_config(
        project_config=project_config,
        local_config=local_config,
        target_name=target_name,
    )
