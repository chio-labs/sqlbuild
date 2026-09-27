"""Run-time detection of project relation names hard-coded in Python SQL."""

from __future__ import annotations

import logging
from collections.abc import Mapping

from sqlbuild.compiler.references.main.extract_relation_names import extract_relation_names
from sqlbuild.compiler.references.main.match_project_relation import match_project_relation
from sqlbuild.compiler.references.main.runtime_project_relations import (
    runtime_project_relations,
)
from sqlbuild.compiler.references.models import (
    ProjectRelation,
    ProjectRelationIndex,
    RelationName,
)
from sqlbuild.python_nodes.models import SqlResourceRef

_LOGGER: logging.Logger = logging.getLogger(__name__)


class RuntimeRelationGuard:
    """Warn when ctx.query() or ctx.execute_sql() SQL hard-codes a project relation name."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        owner_label: str,
        declare_help: str,
        project_relations: Mapping[SqlResourceRef, str],
        dialect: str | None,
        default_database: str | None,
        default_schema: str | None,
        warnings: list[str],
        own_refs: frozenset[SqlResourceRef] = frozenset(),
    ) -> None:
        self._owner_label: str = owner_label
        self._declare_help: str = declare_help
        self._project_relations: Mapping[SqlResourceRef, str] = project_relations
        self._dialect: str | None = dialect
        self._default_database: str | None = default_database
        self._default_schema: str | None = default_schema
        self._warnings: list[str] = warnings
        self._resolved_refs: set[SqlResourceRef] = set(own_refs)
        self._reported_refs: set[SqlResourceRef] = set()
        self._temporary_names: set[str] = set()
        self._index: ProjectRelationIndex | None = None

    def record_resolved(self, ref: SqlResourceRef) -> None:
        """Record a relation the node obtained through ctx.relation()."""

        self._resolved_refs.add(ref)

    def check(self, sql: str) -> None:
        """Warn once per project relation that ``sql`` names without ctx.relation()."""

        extracted: tuple[tuple[RelationName, ...], frozenset[str]] | None = extract_relation_names(
            sql=sql, dialect=self._dialect
        )
        if extracted is None:
            _LOGGER.debug(
                "%s sent SQL that could not be parsed for hard-coded relation names",
                self._owner_label,
            )
            return
        relations, temporary = extracted
        self._temporary_names.update(temporary)
        for relation in relations:
            if relation.schema is None and relation.name.casefold() in self._temporary_names:
                continue
            match: ProjectRelation | None = match_project_relation(
                index=self._relation_index(),
                relation=relation,
                default_database=self._default_database,
                default_schema=self._default_schema,
            )
            if (
                match is None
                or match.ref in self._resolved_refs
                or match.ref in self._reported_refs
            ):
                continue
            self._reported_refs.add(match.ref)
            self._warnings.append(self._warning(match=match, relation=relation))

    def _relation_index(self) -> ProjectRelationIndex:
        if self._index is None:
            self._index = runtime_project_relations(
                relations=self._project_relations, dialect=self._dialect
            )
        return self._index

    def _warning(self, *, match: ProjectRelation, relation: RelationName) -> str:
        typed: str = f'{match.ref.kind.value}("{match.ref.name}")'
        written: str = ".".join(
            part for part in (relation.database, relation.schema, relation.name) if part
        )
        return (
            f"[P008] {self._owner_label} named {match.ref.kind.value}:{match.ref.name} as "
            f"'{written}' in SQL without ctx.relation(); "
            f"{self._declare_help.format(typed=typed)} and use ctx.relation({typed}), or set "
            "[references] enforce_explicit = false"
        )
