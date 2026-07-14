"""Resolve dbt configuration."""

from pathlib import Path

from sqlbuild.integrations.dbt.helpers.config.core import resolve_dbt_config as _resolve
from sqlbuild.integrations.dbt.models import DbtCliConfigOverrides, ResolvedDbtConfig
from sqlbuild.spec.contracts.models import DbtConfig, LocalDbtConfig


def resolve_dbt_config(
    *,
    project_root: Path,
    config: DbtConfig,
    overrides: DbtCliConfigOverrides,
    require_project_dir: bool,
    local_config: LocalDbtConfig | None = None,
) -> ResolvedDbtConfig:
    """Resolve dbt config from overrides and project configuration."""

    return _resolve(
        project_root=project_root,
        config=config,
        overrides=overrides,
        require_project_dir=require_project_dir,
        local_config=local_config,
    )
