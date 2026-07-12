from __future__ import annotations

from typing import Any, ClassVar

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.models import RelationInfo


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
        self.list_relations_calls.append((database, tuple(schemas) if schemas is not None else ()))
        requested: frozenset[str] | None = frozenset(schemas) if schemas is not None else None
        return tuple(
            relation
            for relation in self._relations
            if relation.database == database and (requested is None or relation.schema in requested)
        )
