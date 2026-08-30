"""Best-effort fingerprint propagation for clone operations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import RelationLookup
from sqlbuild.adapter.relations.main.relation_lookup import build_relation_lookup
from sqlbuild.compiler.fingerprints.constants import (
    FINGERPRINT_TABLE_NAME,
    NODE_TYPE_MODEL,
    NODE_TYPE_SEED,
)
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
        connection=destination_connection,
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
        connection=destination_connection,
        run_id=run_id,
    )


def _copy_entry_fingerprints(
    *,
    node_type: str,
    origin_entries: Sequence[ModelPlanEntry | SeedPlanEntry],
    destination_entries: Sequence[ModelPlanEntry | SeedPlanEntry],
    successful_names: frozenset[str],
    adapter: BaseAdapter,
    connection: Any,
    run_id: str,
) -> None:
    origin_by_name: dict[str, ModelPlanEntry | SeedPlanEntry] = {
        entry.name: entry for entry in origin_entries
    }
    destination_by_name: dict[str, ModelPlanEntry | SeedPlanEntry] = {
        entry.name: entry for entry in destination_entries
    }
    origin_fingerprint_sets: dict[tuple[str | None, str], FingerprintSet] = (
        _read_origin_fingerprint_sets(
            origin_entries=origin_entries,
            adapter=adapter,
            connection=connection,
        )
    )
    name: str
    for name in sorted(successful_names):
        origin_entry: ModelPlanEntry | SeedPlanEntry | None = origin_by_name.get(name)
        destination_entry: ModelPlanEntry | SeedPlanEntry | None = destination_by_name.get(name)
        if origin_entry is None or destination_entry is None:
            continue
        fingerprint: Fingerprint | None = _lookup_origin_fingerprint(
            node_type=node_type,
            entry=origin_entry,
            origin_fingerprint_sets=origin_fingerprint_sets,
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
            connection=connection,
            execute=adapter.execute,
            database=destination_entry.destination.database,
            schema=destination_entry.destination.schema,
            fingerprint=copied_fingerprint,
            render_qualified_name=adapter.render_qualified_name,
            render_framework_type=adapter.render_framework_type,
            render_create_table_sql=adapter.render_create_fingerprint_table_sql,
            render_create_index_sqls=adapter.render_create_fingerprint_index_sqls,
        )


def _read_origin_fingerprint_sets(
    *,
    origin_entries: Sequence[ModelPlanEntry | SeedPlanEntry],
    adapter: BaseAdapter,
    connection: Any,
) -> dict[tuple[str | None, str], FingerprintSet]:
    """Read each distinct origin (database, schema) fingerprint state once."""

    fingerprint_table_lookup: RelationLookup = build_relation_lookup(
        adapter=adapter,
        connection=connection,
        locations=tuple(
            (entry.destination.database, entry.destination.schema, FINGERPRINT_TABLE_NAME)
            for entry in origin_entries
            if entry.destination.schema is not None
        ),
    )
    fingerprint_sets: dict[tuple[str | None, str], FingerprintSet] = {}
    entry: ModelPlanEntry | SeedPlanEntry
    for entry in origin_entries:
        schema: str | None = entry.destination.schema
        if schema is None:
            continue
        cache_key: tuple[str | None, str] = (entry.destination.database, schema)
        if cache_key in fingerprint_sets:
            continue
        fingerprint_sets[cache_key] = read_latest_fingerprints(
            connection=connection,
            execute=adapter.execute,
            table_exists=fingerprint_table_lookup.exists(
                database=entry.destination.database,
                schema=schema,
                name=FINGERPRINT_TABLE_NAME,
            ),
            database=entry.destination.database,
            schema=schema,
            render_qualified_name=adapter.render_qualified_name,
            render_read_latest_sql=adapter.render_read_latest_fingerprints_sql,
        )
    return fingerprint_sets


def _lookup_origin_fingerprint(
    *,
    node_type: str,
    entry: ModelPlanEntry | SeedPlanEntry,
    origin_fingerprint_sets: dict[tuple[str | None, str], FingerprintSet],
) -> Fingerprint | None:
    schema: str | None = entry.destination.schema
    if schema is None:
        return None
    fingerprint_set: FingerprintSet | None = origin_fingerprint_sets.get(
        (entry.destination.database, schema)
    )
    if fingerprint_set is None:
        return None
    return (fingerprint_set.fingerprints_by_identity or {}).get((node_type, entry.name))
