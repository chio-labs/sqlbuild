from __future__ import annotations

from collections.abc import Callable
from types import MappingProxyType
from typing import Any, ClassVar, cast

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import RelationInfo


class RecordingRelationAdapter(BaseAdapter):
    """Adapter double that records list_relations calls for relation-lookup tests."""

    adapter_name: ClassVar[str] = "recording_relation"

    def __init__(self, *, relations: tuple[RelationInfo, ...]) -> None:
        self._relations = relations
        self.list_relations_calls: list[tuple[str | None, tuple[str, ...]]] = []

    def connect(self, config: dict[str, Any]) -> object:
        del config
        return object()

    def close(self, connection: Any) -> None:
        del connection

    def execute(self, connection: Any, sql: str) -> None:
        del connection, sql

    def list_relations(
        self,
        connection: Any,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None = None,
    ) -> tuple[RelationInfo, ...]:
        del connection, names
        self.list_relations_calls.append(
            (database, _SCHEMA_TUPLE_BUILDERS[schemas is None](schemas))
        )
        matcher: Callable[[RelationInfo], bool] = _RELATION_MATCHER_BUILDERS[schemas is None](
            database, schemas
        )
        relations: list[RelationInfo] = []
        relation: RelationInfo
        for relation in self._relations:
            _RELATION_COLLECTORS[matcher(relation)](relations, relation)
        return tuple(relations)


def _schema_tuple(schemas: tuple[str, ...] | None) -> tuple[str, ...]:
    return cast(tuple[str, ...], schemas)


def _empty_schema_tuple(schemas: tuple[str, ...] | None) -> tuple[str, ...]:
    del schemas
    return ()


def _schema_relation_matcher(
    database: str | None, schemas: tuple[str, ...] | None
) -> Callable[[RelationInfo], bool]:
    requested: frozenset[str] = frozenset(cast(tuple[str, ...], schemas))

    def matches(relation: RelationInfo) -> bool:
        return relation.database == database and relation.schema in requested

    return matches


def _database_relation_matcher(
    database: str | None, schemas: tuple[str, ...] | None
) -> Callable[[RelationInfo], bool]:
    del schemas

    def matches(relation: RelationInfo) -> bool:
        return relation.database == database

    return matches


def _append_relation(relations: list[RelationInfo], relation: RelationInfo) -> None:
    relations.append(relation)


def _ignore_relation(relations: list[RelationInfo], relation: RelationInfo) -> None:
    del relations, relation


_SCHEMA_TUPLE_BUILDERS: MappingProxyType[
    bool, Callable[[tuple[str, ...] | None], tuple[str, ...]]
] = MappingProxyType({False: _schema_tuple, True: _empty_schema_tuple})
_RELATION_MATCHER_BUILDERS: MappingProxyType[
    bool,
    Callable[[str | None, tuple[str, ...] | None], Callable[[RelationInfo], bool]],
] = MappingProxyType({False: _schema_relation_matcher, True: _database_relation_matcher})
_RELATION_COLLECTORS: MappingProxyType[bool, Callable[[list[RelationInfo], RelationInfo], None]] = (
    MappingProxyType({False: _ignore_relation, True: _append_relation})
)
