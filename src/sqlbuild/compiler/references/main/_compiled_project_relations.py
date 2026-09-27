"""Compile-time project-relation index entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.references._helpers.project_relations import compiled_project_relations_impl
from sqlbuild.compiler.references.models import ProjectRelationIndex


def compiled_project_relations(*, project: CompiledProject) -> ProjectRelationIndex:
    """Return the project relations a compiled project declares."""

    return compiled_project_relations_impl(project)
