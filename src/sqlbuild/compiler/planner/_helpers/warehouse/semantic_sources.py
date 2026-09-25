"""Complete missing source metadata in bounded, database-grouped batches."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import ColumnInfo, RelationInfo
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.planner.types import ContractPolicy
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.spec.contracts.models import SourceEntry


def get_semantic_source_columns(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
    source_read_map: dict[str, SourceEntry],
    columns: dict[str, tuple[ColumnInfo, ...]],
    selected_keys: frozenset[CompiledObjectKey],
) -> dict[str, tuple[ColumnInfo, ...]]:
    """Reuse collected columns and inspect only selected, unresolved table sources."""
    if not project.settings.sql_analysis or connection is None:
        return columns
    required: set[str] = set()
    for model in project.models:
        if model.key in selected_keys and model.config.values.get("sql_analysis") is not False:
            required.update(
                reference.ref_name
                for reference in model.references
                if reference.ref_kind == SqlReferenceKind.SOURCE
            )
    by_database: dict[str | None, list[SourceEntry]] = {}
    for name in sorted(required - columns.keys()):
        entry: SourceEntry | None = source_read_map.get(name)
        if (
            entry is None
            or entry.expression is not None
            or entry.contract == ContractPolicy.ENFORCED
        ):
            continue
        by_database.setdefault(entry.database, []).append(entry)
    result: dict[str, tuple[ColumnInfo, ...]] = dict(columns)
    for database, entries in by_database.items():
        relations: tuple[RelationInfo, ...] = adapter.list_relations(
            connection=connection,
            database=database,
            schemas=None,
            names=tuple(sorted({entry.table or entry.name for entry in entries})),
        )
        inspected: dict[tuple[str | None, str | None, str], tuple[ColumnInfo, ...]] = (
            adapter.get_columns_for_relations(connection=connection, relations=relations)
        )
        for entry in entries:
            candidates: tuple[RelationInfo, ...] = tuple(
                relation
                for relation in relations
                if relation.name.casefold() == (entry.table or entry.name).casefold()
                and (
                    entry.schema is None
                    or (relation.schema or "").casefold() == entry.schema.casefold()
                )
            )
            if len(candidates) != 1:
                continue
            relation: RelationInfo = candidates[0]
            identity: tuple[str | None, str | None, str] = (
                relation.database.lower() if relation.database else None,
                relation.schema.lower() if relation.schema else None,
                relation.name.lower(),
            )
            if identity in inspected:
                result[entry.name] = inspected[identity]
    return result
