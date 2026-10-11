"""Relation-name extraction and project-relation matching for hard-coded name checks."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.references.models import ProjectRelation, ProjectRelationIndex, RelationName


def extract_relation_names_impl(
    *, sql: str, dialect: str | None
) -> tuple[tuple[RelationName, ...], frozenset[str]] | None:
    """Return relations named in ``sql`` and temporary tables it creates, or None if unparseable."""

    extracted: tuple[list[tuple[str, str | None, str | None]], list[str]] | None = (
        _native.extract_sql_relation_names(sql, dialect)
    )
    if extracted is None:
        return None
    relations, temporary = extracted
    return (
        tuple(
            RelationName(name=name, schema=schema, database=database)
            for name, schema, database in relations
        ),
        frozenset(temporary),
    )


def match_project_relation_impl(
    *,
    index: ProjectRelationIndex,
    relation: RelationName,
    default_database: str | None,
    default_schema: str | None,
) -> ProjectRelation | None:
    """Return the project relation ``relation`` names, resolving missing qualifiers."""

    schema: str | None = relation.schema if relation.schema is not None else default_schema
    database: str | None = relation.database if relation.database is not None else default_database
    for candidate in index.relations:
        target: RelationName = candidate.relation
        if target.name.casefold() != relation.name.casefold():
            continue
        if not _parts_compatible(left=schema, right=target.schema):
            continue
        if not _parts_compatible(left=database, right=target.database):
            continue
        return candidate
    return None


def _parts_compatible(*, left: str | None, right: str | None) -> bool:
    return left is None or right is None or left.casefold() == right.casefold()
