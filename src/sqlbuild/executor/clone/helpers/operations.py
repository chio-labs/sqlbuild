"""Clone execution operations."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import ModelPlanEntry, SeedPlanEntry
from sqlbuild.executor.clone.main.clone_relation_operation import clone_relation_by_names
from sqlbuild.executor.clone.main.recreate_view_operation import recreate_view_by_names
from sqlbuild.executor.clone.models import CloneItemResult
from sqlbuild.shared.helpers.naming import resolve_relation_location_qualified_name


def clone_relation(
    *,
    destination_entry: SeedPlanEntry | ModelPlanEntry,
    origin_entry: SeedPlanEntry | ModelPlanEntry,
    adapter: BaseAdapter,
    origin_connection: Any,
    destination_connection: Any,
    hard_copy: bool,
) -> CloneItemResult:
    return clone_relation_by_names(
        name=destination_entry.name,
        origin_relation=qualified_name(adapter=adapter, entry=origin_entry),
        destination_relation=qualified_name(adapter=adapter, entry=destination_entry),
        origin_exists=relation_exists(
            adapter=adapter, connection=origin_connection, entry=origin_entry
        ),
        adapter=adapter,
        connection=destination_connection,
        hard_copy=hard_copy,
    )


def recreate_view(
    *,
    destination_entry: ModelPlanEntry,
    origin_entry: SeedPlanEntry | ModelPlanEntry,
    adapter: BaseAdapter,
    origin_connection: Any,
    destination_connection: Any,
) -> CloneItemResult:
    return recreate_view_by_names(
        name=destination_entry.name,
        origin_relation=qualified_name(adapter=adapter, entry=origin_entry),
        destination_relation=qualified_name(adapter=adapter, entry=destination_entry),
        view_sql=destination_entry.resolved_sql,
        origin_exists=relation_exists(
            adapter=adapter, connection=origin_connection, entry=origin_entry
        ),
        adapter=adapter,
        connection=destination_connection,
    )


def relation_exists(
    *,
    adapter: BaseAdapter,
    connection: Any,
    entry: SeedPlanEntry | ModelPlanEntry,
) -> bool:
    return adapter.relation_exists(
        connection,
        database=entry.destination.database,
        schema=entry.destination.schema,
        name=entry.destination.name,
    )


def qualified_name(*, adapter: BaseAdapter, entry: SeedPlanEntry | ModelPlanEntry) -> str:
    return resolve_relation_location_qualified_name(adapter=adapter, location=entry.destination)
