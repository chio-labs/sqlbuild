"""Structured facts for explicit-reference enforcement."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.python_nodes.models import SqlResourceRef


@dataclass(frozen=True)
class RelationName:
    """A relation named in SQL text, with any qualifier parts that were written."""

    name: str
    schema: str | None = None
    database: str | None = None


@dataclass(frozen=True)
class ProjectRelation:
    """A relation SQLBuild manages for one project resource."""

    ref: SqlResourceRef
    relation: RelationName


@dataclass(frozen=True)
class ProjectRelationIndex:
    """Every relation name that counts as a project relation for hard-coded name checks."""

    relations: tuple[ProjectRelation, ...] = field(default_factory=tuple)
