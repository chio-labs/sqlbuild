"""Build a single-query origin warehouse snapshot for clone lookups."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.executor.clone.models import CloneOriginSnapshot


def build_clone_origin_snapshot(
    *,
    adapter: BaseAdapter,
    connection: Any,
    origin_locations: tuple[tuple[str | None, str | None, str], ...],
) -> CloneOriginSnapshot:
    """Gather all origin relations in one list_relations call, indexed by schema and name."""

    schemas: tuple[str, ...] = tuple(
        sorted({schema for _, schema, _ in origin_locations if schema is not None})
    )
    if not schemas:
        return CloneOriginSnapshot()
    database: str | None = next(
        (database for database, _, _ in origin_locations if database is not None), None
    )
    relations: tuple[RelationInfo, ...] = adapter.list_relations(
        connection, database=database, schemas=schemas, names=None
    )
    relations_by_key: dict[tuple[str | None, str], RelationInfo] = {
        CloneOriginSnapshot.key(schema=relation.schema, name=relation.name): relation
        for relation in relations
    }
    return CloneOriginSnapshot(relations_by_key=relations_by_key)
