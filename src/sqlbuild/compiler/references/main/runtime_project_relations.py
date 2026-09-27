"""Run-time project-relation index entrypoint."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.compiler.references._helpers.project_relations import runtime_project_relations_impl
from sqlbuild.compiler.references.models import ProjectRelationIndex
from sqlbuild.python_nodes.models import SqlResourceRef


def runtime_project_relations(
    *, relations: Mapping[SqlResourceRef, str], dialect: str | None
) -> ProjectRelationIndex:
    """Return project relations from adapter-rendered runtime relation names."""

    return runtime_project_relations_impl(relations=relations, dialect=dialect)
