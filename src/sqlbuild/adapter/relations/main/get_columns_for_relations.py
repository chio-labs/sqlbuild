"""Adapter-neutral qualified bulk column retrieval."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.models import ColumnInfo, RelationInfo
from sqlbuild.adapter.relations.constants import METADATA_NAME_FILTER_LIMIT


def get_columns_for_relations_bulk(
    *,
    adapter: Any,
    connection: Any,
    relations: tuple[RelationInfo, ...],
) -> dict[tuple[str | None, str | None, str], tuple[ColumnInfo, ...]]:
    """Fetch one bulk column result per database/schema and restore qualified keys."""

    relations_by_scope: dict[tuple[str | None, str | None], list[RelationInfo]] = {}
    relation: RelationInfo
    for relation in relations:
        scope: tuple[str | None, str | None] = (relation.database, relation.schema)
        relations_by_scope.setdefault(scope, []).append(relation)
    return _gather_scope_columns(
        adapter=adapter,
        connection=connection,
        scopes=tuple(relations_by_scope.items()),
        scope_index=0,
        result={},
    )


def _gather_scope_columns(
    *,
    adapter: Any,
    connection: Any,
    scopes: tuple[tuple[tuple[str | None, str | None], list[RelationInfo]], ...],
    scope_index: int,
    result: dict[tuple[str | None, str | None, str], tuple[ColumnInfo, ...]],
) -> dict[tuple[str | None, str | None, str], tuple[ColumnInfo, ...]]:
    if scope_index >= len(scopes):
        return result
    scope, relations = scopes[scope_index]
    database, schema = scope
    columns_by_name: dict[str, tuple[ColumnInfo, ...]] = adapter.get_all_columns(
        connection=connection,
        database=database,
        schemas=None if schema is None else (schema,),
        names=(
            None
            if len(relations) > METADATA_NAME_FILTER_LIMIT
            else tuple(relation.name for relation in relations)
        ),
    )
    normalized_columns: dict[str, tuple[ColumnInfo, ...]] = {
        name.lower(): columns for name, columns in columns_by_name.items()
    }
    relation: RelationInfo
    for relation in relations:
        columns: tuple[ColumnInfo, ...] | None = normalized_columns.get(relation.name.lower())
        if columns is not None:
            result[relation.identity] = columns
    return _gather_scope_columns(
        adapter=adapter,
        connection=connection,
        scopes=scopes,
        scope_index=scope_index + 1,
        result=result,
    )
