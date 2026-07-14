"""Public virtual project rewrite helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledProject, CompiledRelationLocation
from sqlbuild.virtual.executor._helpers.rewrite import rewrite_project_model_locations


def rewrite_virtual_project_model_locations(
    *, project: CompiledProject, rewritten_locations: dict[str, CompiledRelationLocation]
) -> CompiledProject:
    """Rewrite model locations for a virtual execution consumer."""

    return rewrite_project_model_locations(project=project, rewritten_locations=rewritten_locations)
