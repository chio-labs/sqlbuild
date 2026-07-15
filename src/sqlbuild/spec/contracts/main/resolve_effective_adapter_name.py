"""Public effective adapter name resolution operation."""

from sqlbuild.spec.contracts._helpers.project_config import (
    resolve_effective_adapter_name as _resolve_effective_adapter_name,
)
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig


def resolve_effective_adapter_name(
    *, project_config: ProjectConfig, local_config: LocalConfig
) -> str:
    """Resolve the effective adapter name, allowing local override."""

    return _resolve_effective_adapter_name(
        project_config=project_config,
        local_config=local_config,
    )
