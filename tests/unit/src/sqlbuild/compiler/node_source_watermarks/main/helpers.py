from datetime import datetime
from pathlib import Path

from sqlbuild.compiler.compile.models.core import CompiledObjectKey, CompiledRelationLocation
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.node_source_watermarks.main.record_successful import (
    record_successful_node_source_watermark,
)
from sqlbuild.compiler.node_source_watermarks.models import (
    NodeSourceWatermarkExecutionContext,
    NodeSourceWatermarkIdentity,
    NodeSourceWatermarkRecord,
    NodeSourceWatermarkTarget,
    SourceWatermarkEntry,
    WatermarkGraphKey,
    WatermarkGraphNode,
)
from sqlbuild.compiler.node_source_watermarks.types import WatermarkGraphResourceKind
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.compiler.planner.types import MaterializationType, PlanAction, PlanReason
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessIdentity,
    SourceFreshnessRecord,
)
from tests.unit.src.sqlbuild.compiler.node_source_watermarks.main._test_types import (
    NodeSourceWatermarkExecutionContextTestCase,
)


def graph_key(name: str, *, node_type: str = "model") -> WatermarkGraphKey:
    return WatermarkGraphKey(node_type=node_type, node_name=name)


def model_node(name: str, *, materialized: bool) -> WatermarkGraphNode:
    key: WatermarkGraphKey = graph_key(name)
    return WatermarkGraphNode(
        key=key,
        resource_kind=WatermarkGraphResourceKind.MODEL,
        materialized=materialized,
    )


def source_node(name: str) -> WatermarkGraphNode:
    key: WatermarkGraphKey = graph_key(name, node_type="source")
    return WatermarkGraphNode(
        key=key,
        resource_kind=WatermarkGraphResourceKind.SOURCE,
        materialized=False,
    )


def nodes_by_key(*nodes: WatermarkGraphNode) -> dict[WatermarkGraphKey, WatermarkGraphNode]:
    return {node.key: node for node in nodes}


def source_record(
    identity: SourceFreshnessIdentity,
    *,
    data_version: str,
    data_hash: str,
    value_kind: str = "timestamp",
) -> SourceFreshnessRecord:
    return SourceFreshnessRecord(
        source_name=identity.source_name,
        target_database=identity.target_database,
        target_schema=identity.target_schema,
        target_name=identity.target_name,
        run_id="run-1",
        strategy="adapter_metadata",
        value_kind=value_kind,
        data_version=data_version,
        data_version_hash=data_hash,
        observed_at=datetime(2026, 6, 29, 15, 45),
    )


def source_entry(
    identity: SourceFreshnessIdentity,
    *,
    data_version: str,
    data_hash: str,
    value_kind: str = "timestamp",
) -> SourceWatermarkEntry:
    return SourceWatermarkEntry(
        source_name=identity.source_name,
        target_database=identity.target_database,
        target_schema=identity.target_schema,
        target_name=identity.target_name,
        strategy="adapter_metadata",
        value_kind=value_kind,
        data_version=data_version,
        data_version_hash=data_hash,
        observed_at=datetime(2026, 6, 29, 15, 45),
        watermark_kind="direct",
    )


def compiled_model_key(name: str) -> CompiledObjectKey:
    return CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name)


def compiled_source_key(name: str) -> CompiledObjectKey:
    return CompiledObjectKey(resource_type=CompiledResourceType.SOURCE, name=name)


def node_watermark_identity(name: str) -> NodeSourceWatermarkIdentity:
    return NodeSourceWatermarkIdentity(node_type=CompiledResourceType.MODEL.value, node_name=name)


def model_plan_entry(name: str, *, materialization_type: MaterializationType) -> ModelPlanEntry:
    return ModelPlanEntry(
        key=compiled_model_key(name),
        name=name,
        relative_path=Path(f"models/{name}.sql"),
        materialization_type=materialization_type,
        action=PlanAction.CREATE_TABLE,
        reason=PlanReason.FIRST_RUN,
        destination=CompiledRelationLocation(
            database=None,
            schema="main",
            name=name,
            qualified_name=f"main.{name}",
        ),
        fingerprint_query_sql="select 1",
        resolved_sql="select 1",
        logical_ddl="",
        fingerprint_version_hash=f"version-{name}",
    )


def record_upstream_context_if_required(
    *,
    context: NodeSourceWatermarkExecutionContext,
    test_case: NodeSourceWatermarkExecutionContextTestCase,
    upstream_identity: NodeSourceWatermarkIdentity,
) -> None:
    if upstream_identity not in test_case.upstream_node_identities_by_node.get(
        test_case.node_identity, ()
    ):
        return
    record_successful_node_source_watermark(
        context=context,
        node_identity=upstream_identity,
        target=NodeSourceWatermarkTarget(database=None, schema="main", name="a"),
        run_id="run-1",
        node_version_hash="version-a",
        created_at=datetime(2026, 6, 29, 16),
    )


def complete_for_result(result: NodeSourceWatermarkRecord | None) -> bool | None:
    if result is None:
        return None
    return result.payload.complete


def source_hashes_for_result(result: NodeSourceWatermarkRecord | None) -> tuple[str, ...]:
    if result is None:
        return ()
    return tuple(entry.data_version_hash for entry in result.payload.sources)


def unknown_reasons_for_result(result: NodeSourceWatermarkRecord | None) -> tuple[str, ...]:
    if result is None:
        return ()
    return tuple(entry.reason for entry in result.payload.unknown_sources)


def expected_buffered_record_count(
    *,
    test_case: NodeSourceWatermarkExecutionContextTestCase,
    upstream_identity: NodeSourceWatermarkIdentity,
) -> int:
    count: int = 0
    if upstream_identity in test_case.upstream_node_identities_by_node.get(
        test_case.node_identity, ()
    ):
        count += 1
    if test_case.expected_record_written:
        count += 1
    return count
