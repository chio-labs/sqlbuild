"""Public virtual project rewrite helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledProject, CompiledRelationDestination
from sqlbuild.virtual.executor.helpers.rewrite import rewrite_project_model_targets


def rewrite_virtual_project_model_targets(
    *, project: CompiledProject, rewritten_targets: dict[str, CompiledRelationDestination]
) -> CompiledProject:
    """Rewrite model targets for a virtual execution consumer."""

    return rewrite_project_model_targets(project=project, rewritten_targets=rewritten_targets)
