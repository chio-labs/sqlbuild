"""Warehouse source relation listing and column gathering for planning."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import ColumnInfo, RelationInfo, RelationLookup
from sqlbuild.adapter.relations.main.get_columns_for_inspection import get_columns_for_inspection
from sqlbuild.adapter.relations.main.list_relations_for_inspection import (
    list_relations_for_inspection,
)
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.planner.constants import METADATA_NAME_FILTER_LIMIT
from sqlbuild.spec.contracts.models import SourceEntry


def gather_source_columns(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
    source_entries: tuple[SourceEntry, ...] | None = None,
) -> dict[str, tuple[ColumnInfo, ...]]:
    """Gather warehouse columns for all declared sources."""

    return gather_source_inspection(
        project=project,
        adapter=adapter,
        connection=connection,
        source_entries=source_entries,
    )[0]


def gather_source_inspection(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
    source_entries: tuple[SourceEntry, ...] | None,
) -> tuple[dict[str, tuple[ColumnInfo, ...]], frozenset[str]]:
    """Gather source columns and the names of sources the relation listing found."""

    result: dict[str, tuple[ColumnInfo, ...]] = {}
    listed_names: set[str] = set()
    source_schemas: dict[str, set[str]] = {}
    entries: tuple[SourceEntry, ...] = (
        source_entries
        if source_entries is not None
        else tuple(source.source_entry for source in project.sources)
    )
    entry: SourceEntry
    for entry in entries:
        if entry.expression is not None:
            if entry.type_enforcement:
                column_names: tuple[str, ...] = adapter.query_column_names(
                    connection=connection, sql=entry.expression
                )
                result[entry.name] = tuple(ColumnInfo(name=name, type="") for name in column_names)
            continue
        schema: str | None = entry.schema
        if schema is None:
            continue
        db: str | None = entry.database
        db_key: str = db or ""
        source_schemas.setdefault(db_key, set()).add(schema)

    db_key_iter: str
    schemas: set[str]
    for db_key_iter, schemas in source_schemas.items():
        database: str | None = db_key_iter or None
        scoped: dict[str, tuple[str | None, str | None, str]] = {
            entry_iter.name: RelationLookup.key(
                database=database,
                schema=entry_iter.schema,
                name=entry_iter.table if entry_iter.table is not None else entry_iter.name,
            )
            for entry_iter in entries
            if entry_iter.expression is None
            and (entry_iter.database or None) == database
            and entry_iter.schema in schemas
        }
        relations: tuple[RelationInfo, ...] = list_relations_for_inspection(
            adapter=adapter,
            connection=connection,
            database=database,
            schemas=tuple(sorted(schemas)),
            names=_build_source_table_name_filter(
                project=project, database=database, schemas=schemas, source_entries=entries
            ),
        )
        listed_identities: frozenset[tuple[str | None, str | None, str]] = frozenset(
            relation.identity for relation in relations
        )
        listed_names.update(name for name, key in scoped.items() if key in listed_identities)
        wanted: frozenset[tuple[str | None, str | None, str]] = frozenset(scoped.values())
        all_columns: dict[tuple[str | None, str | None, str], tuple[ColumnInfo, ...]] = (
            get_columns_for_inspection(
                adapter=adapter,
                connection=connection,
                relations=tuple(relation for relation in relations if relation.identity in wanted),
            )
        )
        result.update(
            {name: all_columns[key] for name, key in scoped.items() if key in all_columns}
        )

    return result, frozenset(listed_names)


def _build_source_table_name_filter(
    *,
    project: CompiledProject,
    database: str | None,
    schemas: set[str],
    source_entries: tuple[SourceEntry, ...] | None = None,
) -> tuple[str, ...] | None:
    names: set[str] = set()
    entries: tuple[SourceEntry, ...] = (
        source_entries
        if source_entries is not None
        else tuple(source.source_entry for source in project.sources)
    )
    entry: SourceEntry
    for entry in entries:
        if entry.expression is not None or entry.schema not in schemas:
            continue
        if (entry.database or None) != database:
            continue
        names.add(entry.table if entry.table is not None else entry.name)
    if not names or len(names) > METADATA_NAME_FILTER_LIMIT:
        return None
    return tuple(sorted(names))
