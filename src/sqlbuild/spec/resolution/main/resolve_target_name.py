"""Public target name resolution operation."""

from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig
from sqlbuild.spec.resolution._helpers.targets import resolve_target_name as _resolve_target_name


def resolve_target_name(
    *,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    selected_target: str | None,
) -> str | None:
    """Resolve the effective target name."""

    return _resolve_target_name(
        project_config=project_config,
        local_config=local_config,
        selected_target=selected_target,
    )
