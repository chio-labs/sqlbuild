"""Virtual physical-version seeding helpers."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.compiler.planner.types import IncrementalStrategy, PlanAction
from sqlbuild.executor.build.constants import INCREMENTAL_ACTIONS
from sqlbuild.shared.helpers.naming import (
    resolve_destination_qualified_name,
    resolve_qualified_name_parts,
)
from sqlbuild.virtual.state.models import PhysicalRelationAncestryRecord, PhysicalRelationRecord


def seed_virtual_physical_version(
    *,
    adapter: BaseAdapter,
    connection: Any,
    backend: Any,
    state_connection: Any,
    state_schema: str,
    entry: ModelPlanEntry,
    parent_relation: PhysicalRelationRecord | None,
    version_hash: str | None,
) -> None:
    """Seed one incremental physical version target before DML execution."""

    recorder: StatementRecorder = StatementRecorder()
    if not _should_seed_physical_version(entry=entry):
        return
    if parent_relation is None or version_hash is None:
        return
    if parent_relation.version_hash == version_hash:
        return

    adapter.ensure_schema(
        connection,
        database=entry.destination.database,
        schema=entry.destination.schema,
        statement_recorder=recorder,
    )
    target: str = resolve_destination_qualified_name(adapter=adapter, target=entry.destination)
    if adapter.relation_exists(
        connection,
        database=entry.destination.database,
        schema=entry.destination.schema,
        name=entry.destination.name,
    ):
        adapter.drop(
            connection,
            target=target,
            if_exists=True,
            statement_recorder=recorder,
        )
    source: str = resolve_qualified_name_parts(
        adapter=adapter,
        database=parent_relation.database_name,
        schema=parent_relation.schema_name,
        name=parent_relation.relation_name,
    )
    seed_strategy: str = _seed_physical_relation(
        adapter=adapter,
        connection=connection,
        source=source,
        target=target,
        entry=entry,
        statement_recorder=recorder,
    )
    backend.upsert_physical_relation_ancestry(
        state_connection,
        schema=state_schema,
        record=PhysicalRelationAncestryRecord(
            model_name=entry.name,
            version_hash=version_hash,
            parent_model_name=parent_relation.model_name,
            parent_version_hash=parent_relation.version_hash,
            seed_strategy=seed_strategy,
        ),
    )


def _seed_physical_relation(
    *,
    adapter: BaseAdapter,
    connection: Any,
    source: str,
    target: str,
    entry: ModelPlanEntry,
    statement_recorder: StatementRecorder,
) -> str:
    if _requires_append_bounded_seed(entry=entry):
        cursor_start: str = _cursor_start_for_append_seed(entry=entry)
        adapter.create_table_as(
            connection,
            target=target,
            sql=adapter.render_seed_select_before_cursor(
                source=source,
                cursor_column=entry.cursor_column or "",
                cursor_end_exclusive=cursor_start,
                cursor_type=entry.cursor_type,
            ),
            statement_recorder=statement_recorder,
        )
        return "bounded_append_copy"

    if adapter.supports_durable_clone():
        adapter.durable_clone(
            connection,
            source=source,
            target=target,
            statement_recorder=statement_recorder,
        )
        return "durable_clone"

    adapter.create_table_as(
        connection,
        target=target,
        sql=f"SELECT * FROM {source}",
        statement_recorder=statement_recorder,
    )
    return "copy"


def _should_seed_physical_version(*, entry: ModelPlanEntry) -> bool:
    return entry.action in INCREMENTAL_ACTIONS or entry.action == PlanAction.CUSTOM


def _requires_append_bounded_seed(*, entry: ModelPlanEntry) -> bool:
    return (
        entry.incremental_strategy == IncrementalStrategy.APPEND and entry.cursor_bounds is not None
    )


def _cursor_start_for_append_seed(*, entry: ModelPlanEntry) -> str:
    if entry.cursor_column is None or entry.cursor_bounds is None:
        raise PlannerInputError(
            f"bounded append seeding for '{entry.name}' requires cursor bounds and cursor_column"
        )
    return entry.cursor_bounds.start
