"""Project-relation matching entrypoint for hard-coded name checks."""

from __future__ import annotations

from sqlbuild.compiler.references._helpers.relation_names import match_project_relation_impl
from sqlbuild.compiler.references.models import ProjectRelation, ProjectRelationIndex, RelationName


def match_project_relation(
    *,
    index: ProjectRelationIndex,
    relation: RelationName,
    default_database: str | None = None,
    default_schema: str | None = None,
) -> ProjectRelation | None:
    """Return the project relation ``relation`` names, resolving missing qualifiers."""

    return match_project_relation_impl(
        index=index,
        relation=relation,
        default_database=default_database,
        default_schema=default_schema,
    )
