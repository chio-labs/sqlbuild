"""dbt runtime node source watermark helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.main.relation_lookup import build_relation_lookup
from sqlbuild.compiler.fingerprints.constants import NODE_TYPE_DBT
from sqlbuild.compiler.node_source_watermarks.constants import NODE_SOURCE_WATERMARK_TABLE_NAME
from sqlbuild.compiler.node_source_watermarks.main.build_report import (
    build_node_source_watermark_staleness_report,
)
from sqlbuild.compiler.node_source_watermarks.main.classify_staleness import (
    classify_node_source_watermark_staleness,
)
from sqlbuild.compiler.node_source_watermarks.main.context import (
    build_node_source_watermark_execution_context,
)
from sqlbuild.compiler.node_source_watermarks.main.frontier import (
    build_materialized_watermark_frontier,
)
from sqlbuild.compiler.node_source_watermarks.main.read import read_latest_node_source_watermarks
from sqlbuild.compiler.node_source_watermarks.main.record_successful import (
    record_successful_node_source_watermark,
)
from sqlbuild.compiler.node_source_watermarks.main.render_report import (
    format_node_source_watermark_staleness_report,
)
from sqlbuild.compiler.node_source_watermarks.main.source_ancestry import (
    build_watermark_source_ancestry,
)
from sqlbuild.compiler.node_source_watermarks.main.write import write_node_source_watermark_records
from sqlbuild.compiler.node_source_watermarks.models import (
    NodeSourceWatermarkExecutionContext,
    NodeSourceWatermarkIdentity,
    NodeSourceWatermarkSet,
    NodeSourceWatermarkStaleness,
    NodeSourceWatermarkStalenessReport,
    NodeSourceWatermarkTarget,
    WatermarkFrontierMember,
    WatermarkGraphKey,
    WatermarkGraphNode,
    WatermarkSourceAncestryMember,
)
from sqlbuild.compiler.node_source_watermarks.types import WatermarkGraphResourceKind
from sqlbuild.compiler.source_freshness.models import SourceFreshnessIdentity, SourceFreshnessRecord
from sqlbuild.integrations.dbt.constants import DBT_MATERIALIZATION_VIEW
from sqlbuild.integrations.dbt.helpers.manifest.core import dbt_manifest_model_materialization
from sqlbuild.integrations.dbt.manifest.models import (
    DbtManifestIndex,
    DbtManifestModel,
    DbtManifestSource,
)
from sqlbuild.integrations.dbt.models import (
    DbtCombinedGraph,
    DbtCombinedGraphKey,
    DbtNodeExecutionResult,
)
from sqlbuild.integrations.dbt.types import (
    DbtCombinedGraphOwner,
    DbtCombinedGraphResourceType,
    DbtSupportedResourceType,
)
from sqlbuild.shared.models import RelationLookup


def build_dbt_node_source_watermark_context(
    *,
    manifest: DbtManifestIndex,
    graph: DbtCombinedGraph,
    source_records: tuple[SourceFreshnessRecord, ...],
    adapter: BaseAdapter,
    connection: Any,
    state_database: str | None,
    state_schema: str | None,
) -> NodeSourceWatermarkExecutionContext | None:
    """Build dbt node source watermark context for one dbt execution."""

    if state_schema is None or not source_records:
        return None
    nodes: dict[WatermarkGraphKey, WatermarkGraphNode] = _nodes_by_key(manifest=manifest)
    upstream_deps: dict[WatermarkGraphKey, tuple[WatermarkGraphKey, ...]] = _upstream_deps(
        graph=graph,
        nodes=nodes,
    )
    materialized_node_keys: frozenset[WatermarkGraphKey] = frozenset(
        node.key
        for node in nodes.values()
        if node.resource_kind == WatermarkGraphResourceKind.MODEL and node.materialized
    )
    if not materialized_node_keys:
        return None
    return build_node_source_watermark_execution_context(
        latest_watermarks=_read_latest_watermarks(
            adapter=adapter,
            connection=connection,
            state_database=state_database,
            state_schema=state_schema,
        ),
        direct_source_records={record.identity: record for record in source_records},
        direct_source_identities_by_node=_direct_source_identities_by_node(
            node_keys=materialized_node_keys,
            upstream_deps=upstream_deps,
            nodes=nodes,
            manifest=manifest,
        ),
        source_identities_by_node=_source_identities_by_node(
            node_keys=materialized_node_keys,
            upstream_deps=upstream_deps,
            nodes=nodes,
            manifest=manifest,
        ),
        upstream_node_identities_by_node=_upstream_node_identities_by_node(
            node_keys=materialized_node_keys,
            upstream_deps=upstream_deps,
            nodes=nodes,
        ),
    )


def record_dbt_successful_node_source_watermark(
    *,
    context: NodeSourceWatermarkExecutionContext | None,
    result: DbtNodeExecutionResult,
    manifest: DbtManifestIndex,
    run_id: str,
    node_version_hash: str | None,
) -> None:
    """Buffer a dbt node source watermark record for one successful dbt model."""

    if context is None or result.resource_type != DbtSupportedResourceType.MODEL:
        return
    if result.status.lower() not in {"ok", "success", "pass", "passed"}:
        return
    model: DbtManifestModel | None = manifest.models_by_unique_id.get(result.unique_id)
    if model is None or _model_is_view(model):
        return
    record_successful_node_source_watermark(
        context=context,
        node_identity=_node_identity(result.unique_id),
        target=NodeSourceWatermarkTarget(
            database=result.database if result.database is not None else model.database,
            schema=result.schema if result.schema is not None else model.schema,
            name=result.relation_name or model.alias or model.name,
        ),
        run_id=run_id,
        node_version_hash=node_version_hash or result.node_checksum or model.definition_fingerprint,
        created_at=datetime.now(tz=UTC),
    )


def write_dbt_node_source_watermark_records(
    *,
    context: NodeSourceWatermarkExecutionContext | None,
    adapter: BaseAdapter,
    connection: Any,
    state_database: str | None,
    state_schema: str | None,
) -> None:
    """Write buffered dbt node source watermark records to the dbt state schema."""

    if context is None or state_schema is None or not context.buffered_records:
        return
    write_node_source_watermark_records(
        connection=connection,
        execute=adapter.execute,
        database=state_database,
        schema=state_schema,
        records=tuple(context.buffered_records),
        render_create_table_sql=adapter.render_create_node_source_watermark_table_sql,
        render_insert_records_sql=adapter.render_insert_node_source_watermark_records_sql,
    )


def build_dbt_node_source_watermark_staleness_warning(
    *,
    manifest: DbtManifestIndex,
    graph: DbtCombinedGraph,
    selected_unique_ids: tuple[str, ...],
    source_records: tuple[SourceFreshnessRecord, ...],
    adapter: BaseAdapter,
    connection: Any,
    state_database: str | None,
    state_schema: str | None,
) -> str | None:
    """Build one grouped dbt warning for stale materialized frontier source proofs."""

    if state_schema is None or not source_records or not selected_unique_ids:
        return None
    nodes: dict[WatermarkGraphKey, WatermarkGraphNode] = _nodes_by_key(manifest=manifest)
    upstream_deps: dict[WatermarkGraphKey, tuple[WatermarkGraphKey, ...]] = _upstream_deps(
        graph=graph,
        nodes=nodes,
    )
    root_keys: frozenset[WatermarkGraphKey] = frozenset(
        key
        for unique_id in selected_unique_ids
        if unique_id in manifest.models_by_unique_id
        and (key := _graph_key(unique_id=unique_id, resource_kind=WatermarkGraphResourceKind.MODEL))
        in nodes
    )
    materialized_node_keys: frozenset[WatermarkGraphKey] = frozenset(
        node.key
        for node in nodes.values()
        if node.resource_kind == WatermarkGraphResourceKind.MODEL and node.materialized
    )
    frontier_members: tuple[WatermarkFrontierMember, ...] = tuple(
        member
        for member in build_materialized_watermark_frontier(
            root_keys=root_keys,
            upstream_deps=upstream_deps,
            nodes=nodes,
        )
        if (frontier_node := nodes.get(member.frontier_key)) is not None
        and frontier_node.resource_kind == WatermarkGraphResourceKind.MODEL
        and frontier_node.materialized
    )
    if not frontier_members:
        return None
    current_records: dict[SourceFreshnessIdentity, SourceFreshnessRecord] = {
        record.identity: record for record in source_records
    }
    classifications: tuple[NodeSourceWatermarkStaleness, ...] = (
        classify_node_source_watermark_staleness(
            frontier_members=frontier_members,
            nodes=nodes,
            source_identities_by_key=_source_identities_by_key(manifest=manifest),
            required_source_identities_by_node=_source_identities_by_node(
                node_keys=materialized_node_keys,
                upstream_deps=upstream_deps,
                nodes=nodes,
                manifest=manifest,
            ),
            current_source_records=current_records,
            watermark_records=_read_latest_watermarks(
                adapter=adapter,
                connection=connection,
                state_database=state_database,
                state_schema=state_schema,
            ).records,
        )
    )
    report: NodeSourceWatermarkStalenessReport = build_node_source_watermark_staleness_report(
        classifications=classifications
    )
    message: str = format_node_source_watermark_staleness_report(report=report)
    return message or None


def _nodes_by_key(*, manifest: DbtManifestIndex) -> dict[WatermarkGraphKey, WatermarkGraphNode]:
    nodes: dict[WatermarkGraphKey, WatermarkGraphNode] = {}
    model: DbtManifestModel
    for model in manifest.models_by_unique_id.values():
        key: WatermarkGraphKey = _graph_key(
            unique_id=model.unique_id, resource_kind=WatermarkGraphResourceKind.MODEL
        )
        nodes[key] = WatermarkGraphNode(
            key=key,
            resource_kind=WatermarkGraphResourceKind.MODEL,
            materialized=not _model_is_view(model),
        )
    source: DbtManifestSource
    for source in manifest.sources_by_unique_id.values():
        key = _graph_key(
            unique_id=source.unique_id, resource_kind=WatermarkGraphResourceKind.SOURCE
        )
        nodes[key] = WatermarkGraphNode(
            key=key,
            resource_kind=WatermarkGraphResourceKind.SOURCE,
        )
    return nodes


def _upstream_deps(
    *, graph: DbtCombinedGraph, nodes: dict[WatermarkGraphKey, WatermarkGraphNode]
) -> dict[WatermarkGraphKey, tuple[WatermarkGraphKey, ...]]:
    deps: dict[WatermarkGraphKey, tuple[WatermarkGraphKey, ...]] = {}
    key: DbtCombinedGraphKey
    upstream_keys: tuple[DbtCombinedGraphKey, ...]
    for key, upstream_keys in graph.upstream_deps.items():
        if key.owner != DbtCombinedGraphOwner.DBT:
            continue
        graph_key: WatermarkGraphKey = _watermark_key_from_combined_key(key)
        if graph_key not in nodes:
            continue
        deps[graph_key] = tuple(
            upstream_graph_key
            for upstream_key in upstream_keys
            if upstream_key.owner == DbtCombinedGraphOwner.DBT
            and (upstream_graph_key := _watermark_key_from_combined_key(upstream_key)) in nodes
        )
    return deps


def _source_identities_by_node(
    *,
    node_keys: frozenset[WatermarkGraphKey],
    upstream_deps: dict[WatermarkGraphKey, tuple[WatermarkGraphKey, ...]],
    nodes: dict[WatermarkGraphKey, WatermarkGraphNode],
    manifest: DbtManifestIndex,
) -> dict[NodeSourceWatermarkIdentity, tuple[SourceFreshnessIdentity, ...]]:
    result: dict[NodeSourceWatermarkIdentity, list[SourceFreshnessIdentity]] = {}
    member: WatermarkSourceAncestryMember
    for member in build_watermark_source_ancestry(
        node_keys=node_keys,
        upstream_deps=upstream_deps,
        nodes=nodes,
    ):
        source: DbtManifestSource | None = manifest.sources_by_unique_id.get(
            member.source_key.node_name
        )
        if source is None:
            continue
        result.setdefault(_identity_from_graph_key(member.node_key), []).append(
            _source_identity(source)
        )
    return {
        identity: tuple(sorted(source_identities, key=_source_identity_sort_key))
        for identity, source_identities in result.items()
    }


def _source_identities_by_key(
    *, manifest: DbtManifestIndex
) -> dict[WatermarkGraphKey, SourceFreshnessIdentity]:
    return {
        _graph_key(
            unique_id=source.unique_id, resource_kind=WatermarkGraphResourceKind.SOURCE
        ): _source_identity(source)
        for source in manifest.sources_by_unique_id.values()
    }


def _direct_source_identities_by_node(
    *,
    node_keys: frozenset[WatermarkGraphKey],
    upstream_deps: dict[WatermarkGraphKey, tuple[WatermarkGraphKey, ...]],
    nodes: dict[WatermarkGraphKey, WatermarkGraphNode],
    manifest: DbtManifestIndex,
) -> dict[NodeSourceWatermarkIdentity, tuple[SourceFreshnessIdentity, ...]]:
    result: dict[NodeSourceWatermarkIdentity, list[SourceFreshnessIdentity]] = {}
    member: WatermarkFrontierMember
    for member in build_materialized_watermark_frontier(
        root_keys=node_keys,
        upstream_deps=upstream_deps,
        nodes=nodes,
    ):
        frontier_node: WatermarkGraphNode | None = nodes.get(member.frontier_key)
        if (
            frontier_node is None
            or frontier_node.resource_kind != WatermarkGraphResourceKind.SOURCE
        ):
            continue
        source: DbtManifestSource | None = manifest.sources_by_unique_id.get(
            member.frontier_key.node_name
        )
        if source is None:
            continue
        result.setdefault(_identity_from_graph_key(member.root_key), []).append(
            _source_identity(source)
        )
    return {
        identity: tuple(sorted(source_identities, key=_source_identity_sort_key))
        for identity, source_identities in result.items()
    }


def _upstream_node_identities_by_node(
    *,
    node_keys: frozenset[WatermarkGraphKey],
    upstream_deps: dict[WatermarkGraphKey, tuple[WatermarkGraphKey, ...]],
    nodes: dict[WatermarkGraphKey, WatermarkGraphNode],
) -> dict[NodeSourceWatermarkIdentity, tuple[NodeSourceWatermarkIdentity, ...]]:
    result: dict[NodeSourceWatermarkIdentity, list[NodeSourceWatermarkIdentity]] = {}
    member: WatermarkFrontierMember
    for member in build_materialized_watermark_frontier(
        root_keys=node_keys,
        upstream_deps=upstream_deps,
        nodes=nodes,
    ):
        frontier_node: WatermarkGraphNode | None = nodes.get(member.frontier_key)
        if frontier_node is None or frontier_node.resource_kind != WatermarkGraphResourceKind.MODEL:
            continue
        result.setdefault(_identity_from_graph_key(member.root_key), []).append(
            _identity_from_graph_key(member.frontier_key)
        )
    return {
        identity: tuple(sorted(upstream_identities, key=_node_identity_sort_key))
        for identity, upstream_identities in result.items()
    }


def _read_latest_watermarks(
    *,
    adapter: BaseAdapter,
    connection: Any,
    state_database: str | None,
    state_schema: str,
) -> NodeSourceWatermarkSet:
    relation_lookup: RelationLookup = build_relation_lookup(
        adapter=adapter,
        connection=connection,
        locations=((state_database, state_schema, NODE_SOURCE_WATERMARK_TABLE_NAME),),
    )
    return read_latest_node_source_watermarks(
        connection=connection,
        execute=adapter.execute,
        table_exists=relation_lookup.exists(
            database=state_database,
            schema=state_schema,
            name=NODE_SOURCE_WATERMARK_TABLE_NAME,
        ),
        database=state_database,
        schema=state_schema,
        render_qualified_name=adapter.render_qualified_name,
        render_read_latest_sql=adapter.render_read_latest_node_source_watermarks_sql,
    )


def _watermark_key_from_combined_key(key: DbtCombinedGraphKey) -> WatermarkGraphKey:
    resource_kind: WatermarkGraphResourceKind = (
        WatermarkGraphResourceKind.MODEL
        if key.resource_type == DbtCombinedGraphResourceType.MODEL
        else WatermarkGraphResourceKind.SOURCE
    )
    return _graph_key(unique_id=key.name, resource_kind=resource_kind)


def _graph_key(*, unique_id: str, resource_kind: WatermarkGraphResourceKind) -> WatermarkGraphKey:
    node_type: str = (
        NODE_TYPE_DBT if resource_kind == WatermarkGraphResourceKind.MODEL else resource_kind.value
    )
    return WatermarkGraphKey(node_type=node_type, node_name=unique_id)


def _identity_from_graph_key(key: WatermarkGraphKey) -> NodeSourceWatermarkIdentity:
    return NodeSourceWatermarkIdentity(node_type=NODE_TYPE_DBT, node_name=key.node_name)


def _node_identity(unique_id: str) -> NodeSourceWatermarkIdentity:
    return NodeSourceWatermarkIdentity(node_type=NODE_TYPE_DBT, node_name=unique_id)


def _source_identity(source: DbtManifestSource) -> SourceFreshnessIdentity:
    return SourceFreshnessIdentity(
        source_name=source.unique_id,
        target_database=source.database,
        target_schema=source.schema,
        target_name=source.identifier or source.name,
    )


def _model_is_view(model: DbtManifestModel) -> bool:
    return dbt_manifest_model_materialization(model=model) == DBT_MATERIALIZATION_VIEW


def _node_identity_sort_key(identity: NodeSourceWatermarkIdentity) -> tuple[str, str]:
    return identity.node_type, identity.node_name


def _source_identity_sort_key(identity: SourceFreshnessIdentity) -> tuple[str, str, str, str]:
    return (
        identity.source_name,
        identity.target_database or "",
        identity.target_schema or "",
        identity.target_name or "",
    )
