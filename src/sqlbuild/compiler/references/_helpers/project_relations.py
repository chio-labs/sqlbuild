"""The single owner of which relation names count as project relations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from sqlbuild.compiler.references._helpers.relation_names import (
    extract_relation_names_impl,
)
from sqlbuild.compiler.references.models import ProjectRelation, ProjectRelationIndex, RelationName
from sqlbuild.python_nodes.models import SqlResourceRef


def build_project_relation_index_impl(
    relations: Iterable[ProjectRelation],
) -> ProjectRelationIndex:
    """Return the deduplicated project-relation index for hard-coded name checks."""

    return ProjectRelationIndex(relations=tuple(dict.fromkeys(relations)))


def runtime_project_relations_impl(
    *, relations: Mapping[SqlResourceRef, str], dialect: str | None
) -> ProjectRelationIndex:
    """Return project relations from adapter-rendered runtime relation names."""

    resolved: list[ProjectRelation] = []
    for ref, qualified in relations.items():
        extracted: tuple[tuple[RelationName, ...], frozenset[str]] | None = (
            extract_relation_names_impl(sql=f"SELECT 1 FROM {qualified}", dialect=dialect)
        )
        if extracted is None or len(extracted[0]) != 1:
            continue
        resolved.append(ProjectRelation(ref=ref, relation=extracted[0][0]))
    return build_project_relation_index_impl(resolved)
