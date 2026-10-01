"""Selected-scope validation that external source tables exist in the warehouse."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import RelationInfo
from sqlbuild.adapter.relations.main.list_relations_for_inspection import (
    list_relations_for_inspection,
)
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject, CompiledSource
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.constants import METADATA_NAME_FILTER_LIMIT
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import PlannerRelationsContext, PlannerScope
from sqlbuild.spec.contracts.models import SourceEntry

_MESSAGE_ITEM_LIMIT: int = 10
_WILDCARD_TABLE_CHARACTER: str = "*"


@dataclass(frozen=True)
class _MissingSourceTable:
    source: CompiledSource
    entry: SourceEntry
    read_by: tuple[str, ...]


def check_selected_source_tables_exist(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
    scope: PlannerScope,
    relations: PlannerRelationsContext,
) -> None:
    """Raise when a selected resource reads an external source table that does not exist."""

    readers_by_source: dict[str, list[str]] = _selected_source_readers(scope=scope)
    candidates: list[tuple[CompiledSource, SourceEntry, tuple[str, ...]]] = []
    source: CompiledSource
    for source in project.sources:
        readers: list[str] | None = readers_by_source.get(source.name)
        if not readers:
            continue
        entry: SourceEntry = relations.source_read_map.get(source.name, source.source_entry)
        if not _is_external_table_source(source.source_entry) or not _is_external_table_source(
            entry
        ):
            continue
        candidates.append((source, entry, tuple(sorted(readers))))
    if not candidates:
        return
    existing: frozenset[tuple[str | None, str, str]] = _existing_relation_keys(
        adapter=adapter,
        connection=connection,
        entries=tuple(entry for _, entry, _ in candidates),
    )
    missing: tuple[_MissingSourceTable, ...] = tuple(
        _MissingSourceTable(source=source, entry=entry, read_by=read_by)
        for source, entry, read_by in candidates
        if not _relation_exists(entry=entry, existing=existing)
    )
    if missing:
        raise PlannerInputError(
            _missing_source_tables_message(missing=missing, adapter=adapter),
            code="S405",
            help=_missing_source_tables_help(missing=missing),
        )


def _selected_source_readers(*, scope: PlannerScope) -> dict[str, list[str]]:
    readers_by_source: dict[str, list[str]] = {}
    selected_key: CompiledObjectKey
    for selected_key in scope.selected_keys:
        if selected_key.resource_type == CompiledResourceType.SOURCE:
            continue
        dep_key: CompiledObjectKey
        for dep_key in scope.upstream_deps.get(selected_key, ()):
            if dep_key.resource_type != CompiledResourceType.SOURCE:
                continue
            readers_by_source.setdefault(dep_key.name, []).append(selected_key.name)
    return readers_by_source


def _is_external_table_source(entry: SourceEntry) -> bool:
    return (
        not entry.managed
        and entry.loader is None
        and entry.integration_loader is None
        and entry.expression is None
        and entry.schema is not None
        and _WILDCARD_TABLE_CHARACTER not in _table_name(entry)
    )


def _existing_relation_keys(
    *,
    adapter: BaseAdapter,
    connection: Any,
    entries: tuple[SourceEntry, ...],
) -> frozenset[tuple[str | None, str, str]]:
    names_by_database: dict[str | None, tuple[set[str], set[str]]] = {}
    entry: SourceEntry
    for entry in entries:
        schemas, names = names_by_database.setdefault(entry.database, (set(), set()))
        schemas.add(str(entry.schema))
        names.add(_table_name(entry))
    existing: set[tuple[str | None, str, str]] = set()
    database: str | None
    schemas: set[str]
    names: set[str]
    for database, (schemas, names) in names_by_database.items():
        relations: tuple[RelationInfo, ...] = list_relations_for_inspection(
            adapter=adapter,
            connection=connection,
            database=database,
            schemas=tuple(sorted(schemas)),
            names=tuple(sorted(names)) if len(names) <= METADATA_NAME_FILTER_LIMIT else None,
        )
        relation: RelationInfo
        for relation in relations:
            if relation.schema is None:
                continue
            existing.add(
                (
                    None if database is None else database.lower(),
                    relation.schema.lower(),
                    relation.name.lower(),
                )
            )
    return frozenset(existing)


def _relation_exists(
    *, entry: SourceEntry, existing: frozenset[tuple[str | None, str, str]]
) -> bool:
    return (
        None if entry.database is None else entry.database.lower(),
        str(entry.schema).lower(),
        _table_name(entry).lower(),
    ) in existing


def _table_name(entry: SourceEntry) -> str:
    return entry.table if entry.table is not None else entry.name


def _missing_source_tables_message(
    *, missing: tuple[_MissingSourceTable, ...], adapter: BaseAdapter
) -> str:
    noun: str = "source table" if len(missing) == 1 else "source tables"
    verb: str = "does" if len(missing) == 1 else "do"
    lines: list[str] = [
        f"cannot build selected scope: {len(missing)} {noun} read by selected resources "
        f"{verb} not exist in the warehouse:"
    ]
    item: _MissingSourceTable
    for item in missing[:_MESSAGE_ITEM_LIMIT]:
        relation: str = adapter.render_qualified_name(
            database=item.entry.database,
            schema=item.entry.schema,
            name=_table_name(item.entry),
        ) or ".".join(
            part
            for part in (item.entry.database, item.entry.schema, _table_name(item.entry))
            if part is not None
        )
        readers: str = ", ".join(item.read_by)
        lines.append(f"  - source '{item.source.name}' ({relation}), read by {readers}")
    if len(missing) > _MESSAGE_ITEM_LIMIT:
        lines.append(f"  - ... and {len(missing) - _MESSAGE_ITEM_LIMIT} more")
    return "\n".join(lines)


def _missing_source_tables_help(*, missing: tuple[_MissingSourceTable, ...]) -> str:
    locations: str = ", ".join(
        f"'{item.source.name}' at {_declaration_location(item.source)}"
        for item in missing[:_MESSAGE_ITEM_LIMIT]
    )
    return (
        "create the table, correct its database, schema, or table in the source declaration, "
        f"or stop reading it from the selected models; declared {locations}"
    )


def _declaration_location(source: CompiledSource) -> str:
    path: str = source.source_file.relative_path.as_posix()
    line: int | None = _declaration_line(contents=source.source_file.contents, name=source.name)
    return path if line is None else f"{path}:{line}"


def _declaration_line(*, contents: str, name: str) -> int | None:
    pattern: re.Pattern[str] = re.compile(
        rf"^(?P<indent>\s*)-\s*name:\s*(?P<quote>['\"]?){re.escape(name)}(?P=quote)\s*(#.*)?$"
    )
    best: tuple[int, int] | None = None
    index: int
    line: str
    for index, line in enumerate(contents.splitlines(), start=1):
        match: re.Match[str] | None = pattern.match(line)
        if match is None:
            continue
        indent: int = len(match.group("indent"))
        if best is None or indent < best[0]:
            best = (indent, index)
    return None if best is None else best[1]
