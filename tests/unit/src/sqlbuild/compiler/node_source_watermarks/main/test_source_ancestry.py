from __future__ import annotations

import pytest

from sqlbuild.compiler.node_source_watermarks.main.source_ancestry import (
    build_watermark_source_ancestry,
)
from sqlbuild.compiler.node_source_watermarks.models import (
    WatermarkGraphKey,
    WatermarkSourceAncestryMember,
)
from tests.unit.src.sqlbuild.compiler.node_source_watermarks.main._test_types import (
    WatermarkSourceAncestryResolverTestCase,
)
from tests.unit.src.sqlbuild.compiler.node_source_watermarks.main.helpers import (
    graph_key,
    model_node,
    nodes_by_key,
    source_node,
)

SOURCE_EVENTS: WatermarkGraphKey = graph_key("raw.events", node_type="source")
SOURCE_PAYMENTS: WatermarkGraphKey = graph_key("raw.payments", node_type="source")
MODEL_ROOT: WatermarkGraphKey = graph_key("fact_orders")
MODEL_STAGING_VIEW: WatermarkGraphKey = graph_key("stg_orders")
MODEL_PAYMENTS_TABLE: WatermarkGraphKey = graph_key("stg_payments")


@pytest.mark.parametrize(
    "test_case",
    [
        WatermarkSourceAncestryResolverTestCase(
            description="finds all raw sources through views and materialized nodes",
            node_keys=frozenset({MODEL_ROOT}),
            upstream_deps={
                MODEL_ROOT: (MODEL_STAGING_VIEW, MODEL_PAYMENTS_TABLE),
                MODEL_STAGING_VIEW: (SOURCE_EVENTS,),
                MODEL_PAYMENTS_TABLE: (SOURCE_PAYMENTS,),
            },
            nodes=nodes_by_key(
                model_node("fact_orders", materialized=True),
                model_node("stg_orders", materialized=False),
                model_node("stg_payments", materialized=True),
                source_node("raw.events"),
                source_node("raw.payments"),
            ),
            expected_members=(
                WatermarkSourceAncestryMember(node_key=MODEL_ROOT, source_key=SOURCE_EVENTS),
                WatermarkSourceAncestryMember(node_key=MODEL_ROOT, source_key=SOURCE_PAYMENTS),
            ),
        )
    ],
    ids=["finds all raw sources through views and materialized nodes"],
)
def test_given_watermark_graph_when_resolving_source_ancestry_then_returns_all_raw_source_ancestors(
    test_case: WatermarkSourceAncestryResolverTestCase,
) -> None:
    result: tuple[WatermarkSourceAncestryMember, ...] = build_watermark_source_ancestry(
        node_keys=test_case.node_keys,
        upstream_deps=test_case.upstream_deps,
        nodes=test_case.nodes,
    )

    assert result == test_case.expected_members
