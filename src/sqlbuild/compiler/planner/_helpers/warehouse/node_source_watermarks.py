"""Planner node source watermark state readers."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import RelationLookup
from sqlbuild.adapter.relations.main.relation_lookup import build_relation_lookup
from sqlbuild.compiler.node_source_watermarks.constants import NODE_SOURCE_WATERMARK_TABLE_NAME
from sqlbuild.compiler.node_source_watermarks.main.read import read_latest_node_source_watermarks
from sqlbuild.compiler.node_source_watermarks.models import (
    NodeSourceWatermarkIdentity,
    NodeSourceWatermarkRecord,
    NodeSourceWatermarkSet,
)
from sqlbuild.compiler.planner.models import (
    DependencyBaselinePlanEntry,
    ExistingDestinationInputPlanEntry,
    ModelPlanEntry,
    PlanOutput,
)


def read_latest_node_source_watermarks_for_plan(
    *,
    plan: PlanOutput,
    adapter: BaseAdapter,
    connection: Any,
) -> dict[NodeSourceWatermarkIdentity, NodeSourceWatermarkRecord]:
    """Read latest node source watermark rows from all planned target schemas."""

    records: dict[NodeSourceWatermarkIdentity, NodeSourceWatermarkRecord] = {}
    state_targets: tuple[tuple[str | None, str], ...] = _state_targets(plan=plan)
    relation_lookup: RelationLookup = build_relation_lookup(
        adapter=adapter,
        connection=connection,
        locations=tuple(
            (database, schema, NODE_SOURCE_WATERMARK_TABLE_NAME)
            for database, schema in state_targets
        ),
    )
    for database, schema in state_targets:
        latest: NodeSourceWatermarkSet = read_latest_node_source_watermarks(
            connection=connection,
            execute=adapter.execute,
            table_exists=relation_lookup.exists(
                database=database,
                schema=schema,
                name=NODE_SOURCE_WATERMARK_TABLE_NAME,
            ),
            database=database,
            schema=schema,
            render_qualified_name=adapter.render_qualified_name,
            render_read_latest_sql=adapter.render_read_latest_node_source_watermarks_sql,
        )
        records.update(latest.records)
    return records


def _state_targets(*, plan: PlanOutput) -> tuple[tuple[str | None, str], ...]:
    targets: set[tuple[str | None, str]] = set()
    model_entry: ModelPlanEntry
    for model_entry in plan.model_entries:
        if model_entry.destination.schema is not None:
            targets.add((model_entry.destination.database, model_entry.destination.schema))
    existing_entry: ExistingDestinationInputPlanEntry
    for existing_entry in plan.existing_destination_input_entries:
        if existing_entry.destination.schema is not None:
            targets.add((existing_entry.destination.database, existing_entry.destination.schema))
    baseline_entry: DependencyBaselinePlanEntry
    for baseline_entry in plan.dependency_baseline_entries:
        if baseline_entry.destination.schema is not None:
            targets.add((baseline_entry.destination.database, baseline_entry.destination.schema))
    return tuple(sorted(targets, key=lambda value: (value[0] or "", value[1])))
