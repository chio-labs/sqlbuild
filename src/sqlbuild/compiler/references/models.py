"""Structured facts for explicit-reference enforcement."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.compiler.references.types import HardCodedRelationOwnerKind
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
    compatibility_for: str | None = None


@dataclass(frozen=True)
class ProjectRelationIndex:
    """Every relation name that counts as a project relation for hard-coded name checks."""

    relations: tuple[ProjectRelation, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class LiteralSqlRelation:
    """A relation named in literal SQL in Python code that matched no project relation."""

    owner_label: str
    owner_kind: HardCodedRelationOwnerKind
    relative_path: Path
    line: int
    method: str
    relation: RelationName
