"""Native node source watermark stale-input warning helpers."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.compiler.node_source_watermarks.main.build_report import (
    build_node_source_watermark_staleness_report,
)
from sqlbuild.compiler.node_source_watermarks.main.classify_staleness import (
    classify_node_source_watermark_staleness,
)
from sqlbuild.compiler.node_source_watermarks.main.native_graph import (
    build_native_node_source_watermark_inputs,
)
from sqlbuild.compiler.node_source_watermarks.main.render_report import (
    format_node_source_watermark_staleness_report,
)
from sqlbuild.compiler.node_source_watermarks.models import (
    NativeNodeSourceWatermarkInputs,
    NodeSourceWatermarkIdentity,
    NodeSourceWatermarkRecord,
    NodeSourceWatermarkStaleness,
    NodeSourceWatermarkStalenessReport,
    WatermarkFrontierMember,
    WatermarkGraphNode,
)
from sqlbuild.compiler.node_source_watermarks.types import WatermarkGraphResourceKind
from sqlbuild.compiler.planner.models import PlanOutput, PlanWarning
from sqlbuild.compiler.planner.types import WarningSeverity
from sqlbuild.compiler.source_freshness.models import SourceFreshnessIdentity, SourceFreshnessRecord

_NODE_SOURCE_WATERMARK_WARNING_CODE: str = "S302"


def build_node_source_watermark_staleness_warnings(
    *,
    plan: PlanOutput,
    watermark_records: Mapping[NodeSourceWatermarkIdentity, NodeSourceWatermarkRecord],
) -> tuple[PlanWarning, ...]:
    """Build one grouped warning for stale materialized frontier source proofs."""

    if plan.source_freshness is None:
        return ()
    inputs: NativeNodeSourceWatermarkInputs = build_native_node_source_watermark_inputs(plan=plan)
    frontier_members: tuple[WatermarkFrontierMember, ...] = _materialized_frontier_members(
        inputs=inputs
    )
    if not frontier_members:
        return ()
    current_records: dict[SourceFreshnessIdentity, SourceFreshnessRecord] = {
        record.identity: record for record in plan.source_freshness.observed_records
    }
    classifications: tuple[NodeSourceWatermarkStaleness, ...] = (
        classify_node_source_watermark_staleness(
            frontier_members=frontier_members,
            nodes=inputs.nodes,
            source_identities_by_key=inputs.source_identities_by_key,
            required_source_identities_by_node=inputs.source_identities_by_node,
            current_source_records=current_records,
            watermark_records=watermark_records,
        )
    )
    report: NodeSourceWatermarkStalenessReport = build_node_source_watermark_staleness_report(
        classifications=classifications
    )
    message: str = format_node_source_watermark_staleness_report(report=report)
    if not message:
        return ()
    return (
        PlanWarning(
            model_name=None,
            severity=WarningSeverity.WARNING,
            message=message,
            code=_NODE_SOURCE_WATERMARK_WARNING_CODE,
        ),
    )


def _materialized_frontier_members(
    *, inputs: NativeNodeSourceWatermarkInputs
) -> tuple[WatermarkFrontierMember, ...]:
    members: list[WatermarkFrontierMember] = []
    member: WatermarkFrontierMember
    for member in inputs.frontier_members:
        frontier_node: WatermarkGraphNode | None = inputs.nodes.get(member.frontier_key)
        if (
            frontier_node is not None
            and frontier_node.resource_kind == WatermarkGraphResourceKind.MODEL
            and frontier_node.materialized
        ):
            members.append(member)
    return tuple(members)
