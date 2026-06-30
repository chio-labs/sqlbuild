from __future__ import annotations

import pytest

from sqlbuild.compiler.node_source_watermarks.main.frontier import (
    build_materialized_watermark_frontier,
)
from sqlbuild.compiler.node_source_watermarks.models import (
    WatermarkFrontierMember,
    WatermarkGraphKey,
)
from tests.unit.src.sqlbuild.compiler.node_source_watermarks.main._test_types import (
    WatermarkFrontierResolverTestCase,
)
from tests.unit.src.sqlbuild.compiler.node_source_watermarks.main.helpers import (
    graph_key,
    model_node,
    nodes_by_key,
    source_node,
)

SOURCE_EVENTS: WatermarkGraphKey = graph_key("raw.events", node_type="source")
MODEL_ROOT: WatermarkGraphKey = graph_key("fact_orders")
MODEL_STAGING_VIEW: WatermarkGraphKey = graph_key("stg_orders")
MODEL_DIM_TABLE: WatermarkGraphKey = graph_key("dim_customer")
MODEL_DIM_VIEW: WatermarkGraphKey = graph_key("dim_customer_view")
MODEL_SHARED_TABLE: WatermarkGraphKey = graph_key("shared_orders")
MODEL_SECOND_ROOT: WatermarkGraphKey = graph_key("mart_orders")

FRONTIER_TEST_CASES: list[WatermarkFrontierResolverTestCase] = [
    WatermarkFrontierResolverTestCase(
        description="passes through views and stops at materialized table and source",
        root_keys=frozenset({MODEL_ROOT}),
        upstream_deps={
            MODEL_ROOT: (MODEL_STAGING_VIEW, MODEL_DIM_VIEW),
            MODEL_STAGING_VIEW: (SOURCE_EVENTS,),
            MODEL_DIM_VIEW: (MODEL_DIM_TABLE,),
            MODEL_DIM_TABLE: (SOURCE_EVENTS,),
        },
        nodes=nodes_by_key(
            model_node("fact_orders", materialized=True),
            model_node("stg_orders", materialized=False),
            model_node("dim_customer_view", materialized=False),
            model_node("dim_customer", materialized=True),
            source_node("raw.events"),
        ),
        expected_members=(
            WatermarkFrontierMember(root_key=MODEL_ROOT, frontier_key=MODEL_DIM_TABLE),
            WatermarkFrontierMember(root_key=MODEL_ROOT, frontier_key=SOURCE_EVENTS),
        ),
    ),
    WatermarkFrontierResolverTestCase(
        description="keeps shared frontier member per selected root",
        root_keys=frozenset({MODEL_ROOT, MODEL_SECOND_ROOT}),
        upstream_deps={
            MODEL_ROOT: (MODEL_SHARED_TABLE,),
            MODEL_SECOND_ROOT: (MODEL_SHARED_TABLE,),
            MODEL_SHARED_TABLE: (SOURCE_EVENTS,),
        },
        nodes=nodes_by_key(
            model_node("fact_orders", materialized=True),
            model_node("mart_orders", materialized=True),
            model_node("shared_orders", materialized=True),
            source_node("raw.events"),
        ),
        expected_members=(
            WatermarkFrontierMember(root_key=MODEL_ROOT, frontier_key=MODEL_SHARED_TABLE),
            WatermarkFrontierMember(root_key=MODEL_SECOND_ROOT, frontier_key=MODEL_SHARED_TABLE),
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    FRONTIER_TEST_CASES,
    ids=[case.description for case in FRONTIER_TEST_CASES],
)
def test_given_watermark_graph_when_resolving_frontier_then_returns_materialized_or_source_nodes(
    test_case: WatermarkFrontierResolverTestCase,
) -> None:
    result: tuple[WatermarkFrontierMember, ...] = build_materialized_watermark_frontier(
        root_keys=test_case.root_keys,
        upstream_deps=test_case.upstream_deps,
        nodes=test_case.nodes,
    )

    assert result == test_case.expected_members
