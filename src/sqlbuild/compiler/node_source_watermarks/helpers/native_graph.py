"""Native plan adapter helpers for node source watermark execution inputs."""

from __future__ import annotations

from collections import defaultdict

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.node_source_watermarks.main.frontier import (
    build_materialized_watermark_frontier,
)
from sqlbuild.compiler.node_source_watermarks.main.source_ancestry import (
    build_watermark_source_ancestry,
)
from sqlbuild.compiler.node_source_watermarks.models import (
    NativeNodeSourceWatermarkInputs,
    NodeSourceWatermarkIdentity,
    WatermarkFrontierMember,
    WatermarkGraphKey,
    WatermarkGraphNode,
    WatermarkSourceAncestryMember,
)
from sqlbuild.compiler.node_source_watermarks.types import WatermarkGraphResourceKind
from sqlbuild.compiler.planner.models import (
    DependencyBaselinePlanEntry,
    ExistingDestinationInputPlanEntry,
    ModelPlanEntry,
    PlanOutput,
)
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.compiler.source_freshness.models import SourceFreshnessIdentity
from sqlbuild.spec.models.source import SourceEntry


def build_native_node_source_watermark_inputs(
    *, plan: PlanOutput
) -> NativeNodeSourceWatermarkInputs:
    """Build native execution inputs for node source watermark propagation."""

    nodes: dict[WatermarkGraphKey, WatermarkGraphNode] = _nodes_by_key(plan=plan)
    upstream_deps: dict[WatermarkGraphKey, tuple[WatermarkGraphKey, ...]] = _upstream_deps(
        plan=plan,
        nodes=nodes,
    )
    materialized_node_keys: frozenset[WatermarkGraphKey] = frozenset(
        node.key
        for node in nodes.values()
        if node.resource_kind == WatermarkGraphResourceKind.MODEL and node.materialized
    )
    frontier_members: tuple[WatermarkFrontierMember, ...] = build_materialized_watermark_frontier(
        root_keys=materialized_node_keys,
        upstream_deps=upstream_deps,
        nodes=nodes,
    )
    return NativeNodeSourceWatermarkInputs(
        frontier_members=frontier_members,
        nodes=nodes,
        source_identities_by_key=_source_identities_by_key(source_map=plan.source_map),
        source_identities_by_node=_source_identities_by_node(
            node_keys=materialized_node_keys,
            upstream_deps=upstream_deps,
            nodes=nodes,
            source_map=plan.source_map,
        ),
        direct_source_identities_by_node=_direct_source_identities_by_node(
            node_keys=materialized_node_keys,
            upstream_deps=upstream_deps,
            nodes=nodes,
            source_map=plan.source_map,
        ),
        upstream_node_identities_by_node=_upstream_node_identities_by_node(
            node_keys=materialized_node_keys,
            upstream_deps=upstream_deps,
            nodes=nodes,
        ),
    )


def _nodes_by_key(*, plan: PlanOutput) -> dict[WatermarkGraphKey, WatermarkGraphNode]:
    nodes: dict[WatermarkGraphKey, WatermarkGraphNode] = {}
    model_entry: ModelPlanEntry
    for model_entry in plan.model_entries:
        key: WatermarkGraphKey = _graph_key(model_entry.key)
        nodes[key] = WatermarkGraphNode(
            key=key,
            resource_kind=WatermarkGraphResourceKind.MODEL,
            materialized=model_entry.materialization_type != MaterializationType.VIEW,
        )
    existing_entry: ExistingDestinationInputPlanEntry
    for existing_entry in plan.existing_destination_input_entries:
        key = WatermarkGraphKey(
            node_type=CompiledResourceType.MODEL.value,
            node_name=existing_entry.name,
        )
        nodes.setdefault(
            key,
            WatermarkGraphNode(
                key=key,
                resource_kind=WatermarkGraphResourceKind.MODEL,
                materialized=True,
            ),
        )
    baseline_entry: DependencyBaselinePlanEntry
    for baseline_entry in plan.dependency_baseline_entries:
        key = WatermarkGraphKey(
            node_type=CompiledResourceType.MODEL.value,
            node_name=baseline_entry.name,
        )
        nodes.setdefault(
            key,
            WatermarkGraphNode(
                key=key,
                resource_kind=WatermarkGraphResourceKind.MODEL,
                materialized=baseline_entry.resource_label != MaterializationType.VIEW.value,
            ),
        )
    source_name: str
    for source_name in plan.source_map:
        key = WatermarkGraphKey(node_type=CompiledResourceType.SOURCE.value, node_name=source_name)
        nodes[key] = WatermarkGraphNode(
            key=key,
            resource_kind=WatermarkGraphResourceKind.SOURCE,
            materialized=False,
        )
    return nodes


def _upstream_deps(
    *,
    plan: PlanOutput,
    nodes: dict[WatermarkGraphKey, WatermarkGraphNode],
) -> dict[WatermarkGraphKey, tuple[WatermarkGraphKey, ...]]:
    deps: dict[WatermarkGraphKey, tuple[WatermarkGraphKey, ...]] = {}
    key: CompiledObjectKey
    upstream_keys: tuple[CompiledObjectKey, ...]
    for key, upstream_keys in plan.upstream_deps.items():
        graph_key: WatermarkGraphKey = _graph_key(key)
        if graph_key not in nodes:
            continue
        deps[graph_key] = tuple(
            upstream_graph_key
            for upstream_key in upstream_keys
            if (upstream_graph_key := _graph_key(upstream_key)) in nodes
        )
    return deps


def _source_identities_by_node(
    *,
    node_keys: frozenset[WatermarkGraphKey],
    upstream_deps: dict[WatermarkGraphKey, tuple[WatermarkGraphKey, ...]],
    nodes: dict[WatermarkGraphKey, WatermarkGraphNode],
    source_map: dict[str, SourceEntry],
) -> dict[NodeSourceWatermarkIdentity, tuple[SourceFreshnessIdentity, ...]]:
    result: dict[NodeSourceWatermarkIdentity, list[SourceFreshnessIdentity]] = defaultdict(list)
    member: WatermarkSourceAncestryMember
    for member in build_watermark_source_ancestry(
        node_keys=node_keys,
        upstream_deps=upstream_deps,
        nodes=nodes,
    ):
        source: SourceEntry | None = source_map.get(member.source_key.node_name)
        if source is None:
            continue
        result[_identity_from_graph_key(member.node_key)].append(_source_identity(source))
    return {
        identity: tuple(sorted(source_identities, key=_source_identity_sort_key))
        for identity, source_identities in result.items()
    }


def _source_identities_by_key(
    *, source_map: dict[str, SourceEntry]
) -> dict[WatermarkGraphKey, SourceFreshnessIdentity]:
    return {
        WatermarkGraphKey(
            node_type=CompiledResourceType.SOURCE.value,
            node_name=source_name,
        ): _source_identity(source)
        for source_name, source in source_map.items()
    }


def _upstream_node_identities_by_node(
    *,
    node_keys: frozenset[WatermarkGraphKey],
    upstream_deps: dict[WatermarkGraphKey, tuple[WatermarkGraphKey, ...]],
    nodes: dict[WatermarkGraphKey, WatermarkGraphNode],
) -> dict[NodeSourceWatermarkIdentity, tuple[NodeSourceWatermarkIdentity, ...]]:
    result: dict[NodeSourceWatermarkIdentity, list[NodeSourceWatermarkIdentity]] = defaultdict(list)
    member: WatermarkFrontierMember
    for member in build_materialized_watermark_frontier(
        root_keys=node_keys,
        upstream_deps=upstream_deps,
        nodes=nodes,
    ):
        frontier_node: WatermarkGraphNode | None = nodes.get(member.frontier_key)
        if frontier_node is None or frontier_node.resource_kind != WatermarkGraphResourceKind.MODEL:
            continue
        result[_identity_from_graph_key(member.root_key)].append(
            _identity_from_graph_key(member.frontier_key)
        )
    return {
        identity: tuple(sorted(upstream_identities, key=_node_identity_sort_key))
        for identity, upstream_identities in result.items()
    }


def _direct_source_identities_by_node(
    *,
    node_keys: frozenset[WatermarkGraphKey],
    upstream_deps: dict[WatermarkGraphKey, tuple[WatermarkGraphKey, ...]],
    nodes: dict[WatermarkGraphKey, WatermarkGraphNode],
    source_map: dict[str, SourceEntry],
) -> dict[NodeSourceWatermarkIdentity, tuple[SourceFreshnessIdentity, ...]]:
    result: dict[NodeSourceWatermarkIdentity, list[SourceFreshnessIdentity]] = defaultdict(list)
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
        source: SourceEntry | None = source_map.get(member.frontier_key.node_name)
        if source is None:
            continue
        result[_identity_from_graph_key(member.root_key)].append(_source_identity(source))
    return {
        identity: tuple(sorted(source_identities, key=_source_identity_sort_key))
        for identity, source_identities in result.items()
    }


def _graph_key(key: CompiledObjectKey) -> WatermarkGraphKey:
    return WatermarkGraphKey(node_type=str(key.resource_type), node_name=key.name)


def _identity_from_graph_key(key: WatermarkGraphKey) -> NodeSourceWatermarkIdentity:
    return NodeSourceWatermarkIdentity(node_type=key.node_type, node_name=key.node_name)


def _source_identity(source: SourceEntry) -> SourceFreshnessIdentity:
    return SourceFreshnessIdentity(
        source_name=source.name,
        target_database=source.database,
        target_schema=source.schema,
        target_name=source.table,
    )


def _node_identity_sort_key(identity: NodeSourceWatermarkIdentity) -> tuple[str, str]:
    return identity.node_type, identity.node_name


def _source_identity_sort_key(identity: SourceFreshnessIdentity) -> tuple[str, str, str, str]:
    return (
        identity.source_name,
        identity.target_database or "",
        identity.target_schema or "",
        identity.target_name or "",
    )
