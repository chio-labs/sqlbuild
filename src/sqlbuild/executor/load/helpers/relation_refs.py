"""Relation reference construction for source loaders."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.executor.load.models import LoaderRelationRef
from sqlbuild.shared.helpers.naming import resolve_qualified_name_parts
from sqlbuild.spec.models.source import SourceEntry


def build_loader_relation_refs(
    *,
    adapter: BaseAdapter,
    connection: Any,
    entries: Mapping[Callable[..., object], SourceEntry],
    statement_recorder: StatementRecorder,
) -> dict[Callable[..., object], LoaderRelationRef]:
    return {
        function: build_relation_ref(
            adapter=adapter,
            connection=connection,
            source_entry=entry,
            statement_recorder=statement_recorder,
        )
        for function, entry in entries.items()
    }


def build_source_relation_refs(
    *,
    adapter: BaseAdapter,
    connection: Any,
    entries: Mapping[str, SourceEntry],
    statement_recorder: StatementRecorder,
) -> dict[str, LoaderRelationRef]:
    return {
        name: build_relation_ref(
            adapter=adapter,
            connection=connection,
            source_entry=entry,
            statement_recorder=statement_recorder,
        )
        for name, entry in entries.items()
    }


def build_relation_ref(
    *,
    adapter: BaseAdapter,
    connection: Any,
    source_entry: SourceEntry,
    statement_recorder: StatementRecorder,
) -> LoaderRelationRef:
    destination_name: str = (
        source_entry.table if source_entry.table is not None else source_entry.name
    )
    destination: str = resolve_qualified_name_parts(
        adapter=adapter,
        database=source_entry.database,
        schema=source_entry.schema,
        name=destination_name,
    )
    return LoaderRelationRef(
        name=source_entry.name,
        destination=destination,
        database=source_entry.database,
        schema=source_entry.schema,
        table_name=destination_name,
        cursor_column=source_entry.cursor_column,
        adapter=adapter,
        connection=connection,
        statement_recorder=statement_recorder,
    )
