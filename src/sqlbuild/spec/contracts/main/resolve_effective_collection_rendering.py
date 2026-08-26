"""Public effective collection rendering resolution operation."""

from sqlbuild.spec.contracts._helpers.project_config import (
    resolve_effective_collection_rendering as _resolve_effective_collection_rendering,
)
from sqlbuild.spec.contracts.models import ProjectConfig
from sqlbuild.sql_values.types import CollectionRendering


def resolve_effective_collection_rendering(
    *,
    project_config: ProjectConfig,
    declaration_override: CollectionRendering | None,
) -> CollectionRendering:
    """Resolve declaration rendering over project configuration."""

    return _resolve_effective_collection_rendering(
        project_config=project_config,
        declaration_override=declaration_override,
    )
