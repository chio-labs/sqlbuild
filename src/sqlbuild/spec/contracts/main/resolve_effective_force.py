"""Public effective force resolution operation."""

from sqlbuild.spec.contracts._helpers.targets import (
    resolve_effective_force as _resolve_effective_force,
)
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig


def resolve_effective_force(
    *,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    selected_target: str | None,
    cli_force: bool,
) -> bool:
    """Resolve configured force with CLI, target, and settings precedence."""

    return _resolve_effective_force(
        project_config=project_config,
        local_config=local_config,
        selected_target=selected_target,
        cli_force=cli_force,
    )
