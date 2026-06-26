"""Best-effort fingerprint propagation for clone operations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.fingerprints.constants import NODE_TYPE_MODEL, NODE_TYPE_SEED
from sqlbuild.compiler.fingerprints.main.read import read_latest_fingerprints
from sqlbuild.compiler.fingerprints.main.write import write_fingerprint
from sqlbuild.compiler.fingerprints.models import Fingerprint, FingerprintSet
from sqlbuild.compiler.planner.models import ModelPlanEntry, SeedPlanEntry
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.executor.clone.models import CloneExecutionResult
from sqlbuild.executor.clone.types import CloneAction, CloneStatus


def copy_clone_fingerprints(
    *,
    result: CloneExecutionResult,
    origin_model_entries: tuple[ModelPlanEntry, ...],
    destination_model_entries: tuple[ModelPlanEntry, ...],
    origin_seed_entries: tuple[SeedPlanEntry, ...],
    destination_seed_entries: tuple[SeedPlanEntry, ...],
    adapter: BaseAdapter,
    origin_connection: Any,
    destination_connection: Any,
    run_id: str,
    query_change_tracking: bool,
) -> None:
    """Copy source fingerprints for successfully cloned/copied tables and seeds."""

    if not query_change_tracking:
        return
    successful_names: frozenset[str] = frozenset(
        item.name
        for item in result.item_results
        if item.status == CloneStatus.SUCCESS
        and item.action in {CloneAction.CLONED, CloneAction.COPIED}
    )
    if not successful_names:
        return

    _copy_entry_fingerprints(
        node_type=NODE_TYPE_SEED,
        origin_entries=origin_seed_entries,
        destination_entries=destination_seed_entries,
        successful_names=successful_names,
        adapter=adapter,
        origin_connection=origin_connection,
        destination_connection=destination_connection,
        run_id=run_id,
    )
    table_origin_entries: tuple[ModelPlanEntry, ...] = tuple(
        entry
        for entry in origin_model_entries
        if entry.materialization_type != MaterializationType.VIEW
    )
    table_destination_entries: tuple[ModelPlanEntry, ...] = tuple(
        entry
        for entry in destination_model_entries
        if entry.materialization_type != MaterializationType.VIEW
    )
    _copy_entry_fingerprints(
        node_type=NODE_TYPE_MODEL,
        origin_entries=table_origin_entries,
        destination_entries=table_destination_entries,
        successful_names=successful_names,
        adapter=adapter,
        origin_connection=origin_connection,
        destination_connection=destination_connection,
        run_id=run_id,
    )


def _copy_entry_fingerprints(
    *,
    node_type: str,
    origin_entries: Sequence[ModelPlanEntry | SeedPlanEntry],
    destination_entries: Sequence[ModelPlanEntry | SeedPlanEntry],
    successful_names: frozenset[str],
    adapter: BaseAdapter,
    origin_connection: Any,
    destination_connection: Any,
    run_id: str,
) -> None:
    origin_by_name: dict[str, ModelPlanEntry | SeedPlanEntry] = {
        entry.name: entry for entry in origin_entries
    }
    destination_by_name: dict[str, ModelPlanEntry | SeedPlanEntry] = {
        entry.name: entry for entry in destination_entries
    }
    name: str
    for name in sorted(successful_names):
        origin_entry: ModelPlanEntry | SeedPlanEntry | None = origin_by_name.get(name)
        destination_entry: ModelPlanEntry | SeedPlanEntry | None = destination_by_name.get(name)
        if origin_entry is None or destination_entry is None:
            continue
        fingerprint: Fingerprint | None = _read_origin_fingerprint(
            node_type=node_type,
            entry=origin_entry,
            adapter=adapter,
            connection=origin_connection,
        )
        if fingerprint is None or destination_entry.destination.schema is None:
            continue
        copied_fingerprint: Fingerprint = replace(
            fingerprint,
            target_database=destination_entry.destination.database,
            target_schema=destination_entry.destination.schema,
            target_name=destination_entry.destination.name,
            run_id=run_id,
            ts=datetime.now(tz=UTC),
        )
        write_fingerprint(
            connection=destination_connection,
            execute=adapter.execute,
            database=destination_entry.destination.database,
            schema=destination_entry.destination.schema,
            fingerprint=copied_fingerprint,
            render_qualified_name=adapter.render_qualified_name,
            render_framework_type=adapter.render_framework_type,
            render_create_table_sql=adapter.render_create_fingerprint_table_sql,
            render_create_index_sqls=adapter.render_create_fingerprint_index_sqls,
        )


def _read_origin_fingerprint(
    *,
    node_type: str,
    entry: ModelPlanEntry | SeedPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
) -> Fingerprint | None:
    schema: str | None = entry.destination.schema
    if schema is None:
        return None
    fingerprint_set: FingerprintSet = read_latest_fingerprints(
        connection=connection,
        execute=adapter.execute,
        relation_exists=adapter.relation_exists,
        database=entry.destination.database,
        schema=schema,
        render_qualified_name=adapter.render_qualified_name,
        render_read_latest_sql=adapter.render_read_latest_fingerprints_sql,
    )
    return (fingerprint_set.fingerprints_by_identity or {}).get((node_type, entry.name))
