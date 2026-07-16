"""Public effective changes-only resolution operation."""

from sqlbuild.spec.contracts._helpers.targets import (
    resolve_effective_changes_only as _resolve_effective_changes_only,
)
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig


def resolve_effective_changes_only(
    *,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    selected_target: str | None,
    cli_changes_only: bool,
) -> bool:
    """Resolve changes-only selection with CLI, target, and settings precedence."""

    return _resolve_effective_changes_only(
        project_config=project_config,
        local_config=local_config,
        selected_target=selected_target,
        cli_changes_only=cli_changes_only,
    )
