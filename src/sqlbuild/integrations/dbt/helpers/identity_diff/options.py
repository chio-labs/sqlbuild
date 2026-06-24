"""dbt identity-diff option resolution helpers."""

from __future__ import annotations

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.integrations.dbt.models import DbtCliOptions
from sqlbuild.spec.models.targets import resolve_target_config


def resolve_identity_diff_strict_reuse(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    dbt_options: DbtCliOptions,
    override: bool | None,
) -> bool:
    """Resolve active identity-diff strict reuse behavior."""

    if override is not None:
        return override
    target_name: str | None = dbt_options.target or getattr(
        discovered_inputs.project_config, "default_target", None
    )
    if target_name is None:
        return False
    return resolve_target_config(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        target_name=target_name,
    ).reuse_strict
