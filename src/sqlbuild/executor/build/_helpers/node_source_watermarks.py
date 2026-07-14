"""Native build integration for node source watermark state."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import RelationLookup
from sqlbuild.adapter.relations.main.relation_lookup import build_relation_lookup
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.fingerprints.main.compute_query_hash import compute_query_hash
from sqlbuild.compiler.node_source_watermarks.constants import NODE_SOURCE_WATERMARK_TABLE_NAME
from sqlbuild.compiler.node_source_watermarks.main.context import (
    build_node_source_watermark_execution_context,
)
from sqlbuild.compiler.node_source_watermarks.main.native_graph import (
    build_native_node_source_watermark_inputs,
)
from sqlbuild.compiler.node_source_watermarks.main.read import read_latest_node_source_watermarks
from sqlbuild.compiler.node_source_watermarks.main.record_successful import (
    record_successful_node_source_watermark,
)
from sqlbuild.compiler.node_source_watermarks.main.write import write_node_source_watermark_records
from sqlbuild.compiler.node_source_watermarks.models import (
    NativeNodeSourceWatermarkInputs,
    NodeSourceWatermarkExecutionContext,
    NodeSourceWatermarkIdentity,
    NodeSourceWatermarkRecord,
    NodeSourceWatermarkSet,
    NodeSourceWatermarkTarget,
)
from sqlbuild.compiler.planner.models import ModelPlanEntry, PlanOutput
from sqlbuild.compiler.source_freshness.models import SourceFreshnessIdentity, SourceFreshnessRecord


def build_native_node_source_watermark_context(
    *,
    plan: PlanOutput,
    adapter: BaseAdapter,
    connection: Any,
) -> NodeSourceWatermarkExecutionContext | None:
    """Build native node source watermark context for one build execution."""

    if plan.source_freshness is None:
        return None
    inputs: NativeNodeSourceWatermarkInputs = build_native_node_source_watermark_inputs(plan=plan)
    if not inputs.source_identities_by_node:
        return None
    latest_watermarks: NodeSourceWatermarkSet = _read_latest_watermarks_for_plan(
        plan=plan,
        adapter=adapter,
        connection=connection,
    )
    direct_source_records: dict[SourceFreshnessIdentity, SourceFreshnessRecord] = {
        record.identity: record for record in plan.source_freshness.observed_records
    }
    return build_node_source_watermark_execution_context(
        latest_watermarks=latest_watermarks,
        direct_source_records=direct_source_records,
        direct_source_identities_by_node=inputs.direct_source_identities_by_node,
        source_identities_by_node=inputs.source_identities_by_node,
        upstream_node_identities_by_node=inputs.upstream_node_identities_by_node,
    )


def record_native_successful_node_source_watermark(
    *,
    context: NodeSourceWatermarkExecutionContext | None,
    entry: ModelPlanEntry,
    run_id: str,
) -> None:
    """Buffer a native node source watermark record after successful materialization."""

    if context is None:
        return
    node_identity: NodeSourceWatermarkIdentity = NodeSourceWatermarkIdentity(
        node_type=CompiledResourceType.MODEL.value,
        node_name=entry.name,
    )
    record_successful_node_source_watermark(
        context=context,
        node_identity=node_identity,
        target=NodeSourceWatermarkTarget(
            database=entry.destination.database,
            schema=entry.destination.schema,
            name=entry.destination.name,
        ),
        run_id=run_id,
        node_version_hash=entry.fingerprint_version_hash
        or compute_query_hash(entry.fingerprint_query_sql),
        created_at=datetime.now(tz=UTC),
    )


def write_native_node_source_watermark_records(
    *,
    context: NodeSourceWatermarkExecutionContext | None,
    adapter: BaseAdapter,
    connection: Any,
) -> None:
    """Write buffered native node source watermark records grouped by target schema."""

    if context is None or not context.buffered_records:
        return
    records_by_target: dict[tuple[str | None, str], list[NodeSourceWatermarkRecord]] = defaultdict(
        list
    )
    record: NodeSourceWatermarkRecord
    for record in context.buffered_records:
        if record.target_schema is None:
            continue
        records_by_target[(record.target_database, record.target_schema)].append(record)
    target: tuple[str | None, str]
    records: list[NodeSourceWatermarkRecord]
    for target, records in records_by_target.items():
        database, schema = target
        write_node_source_watermark_records(
            connection=connection,
            execute=adapter.execute,
            database=database,
            schema=schema,
            records=tuple(records),
            render_create_table_sql=adapter.render_create_node_source_watermark_table_sql,
            render_insert_records_sql=adapter.render_insert_node_source_watermark_records_sql,
        )


def _read_latest_watermarks_for_plan(
    *,
    plan: PlanOutput,
    adapter: BaseAdapter,
    connection: Any,
) -> NodeSourceWatermarkSet:
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
    return NodeSourceWatermarkSet(schema="", records=records)


def _state_targets(*, plan: PlanOutput) -> tuple[tuple[str | None, str], ...]:
    targets: set[tuple[str | None, str]] = set()
    entry: ModelPlanEntry
    for entry in plan.model_entries:
        if entry.destination.schema is not None:
            targets.add((entry.destination.database, entry.destination.schema))
    return tuple(sorted(targets, key=lambda value: (value[0] or "", value[1])))
