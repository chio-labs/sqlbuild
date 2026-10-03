"""Selected-scope validation that external source tables exist in the warehouse."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import RelationReadProbe
from sqlbuild.adapter.contract.types import RelationReadStatus
from sqlbuild.adapter.relations.main.run_bounded_inspections import run_bounded_inspections
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject, CompiledSource
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.main._yaml_entry_line import yaml_entry_line
from sqlbuild.compiler.planner._helpers.resolve.sources import render_source_read_relation
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
    probe: RelationReadProbe


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
    unlisted: tuple[tuple[CompiledSource, SourceEntry, tuple[str, ...]], ...] = tuple(
        candidate
        for candidate in candidates
        if candidate[0].name not in relations.listed_source_names
    )
    probes: list[RelationReadProbe] = run_bounded_inspections(
        tasks=tuple(
            partial(
                adapter.probe_relation_read,
                connection=connection,
                relation=render_source_read_relation(adapter=adapter, source_entry=entry),
            )
            for _, entry, _ in unlisted
        ),
        concurrency=max(1, int(adapter.metadata_inspection_concurrency)),
    )
    missing: tuple[_MissingSourceTable, ...] = tuple(
        _MissingSourceTable(source=source, entry=entry, read_by=read_by, probe=probe)
        for (source, entry, read_by), probe in zip(unlisted, probes, strict=True)
        if probe.status != RelationReadStatus.READABLE
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


def _table_name(entry: SourceEntry) -> str:
    return entry.table if entry.table is not None else entry.name


def _missing_source_tables_message(
    *, missing: tuple[_MissingSourceTable, ...], adapter: BaseAdapter
) -> str:
    noun: str = "source table" if len(missing) == 1 else "source tables"
    verb: str = "does" if len(missing) == 1 else "do"
    readability: str = (
        " or is not readable by the current role"
        if len(missing) == 1
        else " or are not readable by the current role"
    )
    lines: list[str] = [
        f"cannot build selected scope: {len(missing)} {noun} read by selected resources "
        f"{verb} not exist in the warehouse"
        f"{readability if _any_unreadable(missing) else ''}:"
    ]
    item: _MissingSourceTable
    for item in missing[:_MESSAGE_ITEM_LIMIT]:
        relation: str = render_source_read_relation(adapter=adapter, source_entry=item.entry)
        readers: str = ", ".join(item.read_by)
        lines.append(
            f"  - source '{item.source.name}' ({relation}), read by {readers}"
            f"{_unreadable_suffix(item.probe)}"
        )
    if len(missing) > _MESSAGE_ITEM_LIMIT:
        lines.append(f"  - ... and {len(missing) - _MESSAGE_ITEM_LIMIT} more")
    return "\n".join(lines)


def _unreadable_suffix(probe: RelationReadProbe) -> str:
    if probe.status != RelationReadStatus.MISSING_OR_UNREADABLE:
        return ""
    role: str = f"role {probe.role}" if probe.role is not None else "the current role"
    return f"; the warehouse reports it does not exist or is not readable by {role}"


def _any_unreadable(missing: tuple[_MissingSourceTable, ...]) -> bool:
    return any(item.probe.status == RelationReadStatus.MISSING_OR_UNREADABLE for item in missing)


def _missing_source_tables_help(*, missing: tuple[_MissingSourceTable, ...]) -> str:
    locations: str = ", ".join(
        f"'{item.source.name}' at {_declaration_location(item.source)}"
        for item in missing[:_MESSAGE_ITEM_LIMIT]
    )
    roles: tuple[str, ...] = tuple(
        sorted({item.probe.role for item in missing if item.probe.role is not None})
    )
    role_text: str = f" ({', '.join(roles)})" if roles else ""
    grant: str = (
        f"grant SELECT on it to the role in use{role_text}, " if _any_unreadable(missing) else ""
    )
    return (
        f"create or load the table, {grant}correct its database, schema, or table in the "
        f"source declaration, or stop reading it from the selected models; declared {locations}"
    )


def _declaration_location(source: CompiledSource) -> str:
    path: str = source.source_file.relative_path.as_posix()
    line: int | None = yaml_entry_line(contents=source.source_file.contents, name=source.name)
    return path if line is None else f"{path}:{line}"
