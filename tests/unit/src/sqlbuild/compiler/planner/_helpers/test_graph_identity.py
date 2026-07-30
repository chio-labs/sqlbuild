from __future__ import annotations

import time

import pytest

from sqlbuild.compiler.planner.main.identity._graph_identity import (
    build_expected_graph_identity_hashes,
)
from sqlbuild.compiler.planner.main.identity._graph_write_identity import (
    build_graph_write_identity_hashes,
)
from sqlbuild.compiler.planner.models import GraphIdentityNode, GraphNodeKey
from sqlbuild.compiler.planner.types import GraphResourceKind
from tests.unit.src.sqlbuild.compiler.planner._helpers._test_types import (
    GraphIdentityExpectedHashesTestCase,
    GraphIdentityWriteHashesTestCase,
    GraphIdentityWritePerfTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers.helpers import (
    build_diamond_ladder_identity_nodes,
    compose_hashed_identity,
    compose_readable_identity,
)

MODEL_A: GraphNodeKey = GraphNodeKey(node_type="model", node_name="a")
MODEL_B: GraphNodeKey = GraphNodeKey(node_type="model", node_name="b")
MODEL_C: GraphNodeKey = GraphNodeKey(node_type="model", node_name="c")
MODEL_D: GraphNodeKey = GraphNodeKey(node_type="model", node_name="d")


@pytest.mark.parametrize(
    "test_case",
    [
        GraphIdentityExpectedHashesTestCase(
            description=(
                "uses dependency order and named upstream keys while preserving missing nodes"
            ),
            nodes={
                MODEL_A: GraphIdentityNode(
                    key=MODEL_A,
                    resource_kind=GraphResourceKind.MODEL,
                    upstream_keys=(MODEL_B, MODEL_C),
                    local_hash="local_a",
                ),
                MODEL_B: GraphIdentityNode(
                    key=MODEL_B,
                    resource_kind=GraphResourceKind.MODEL,
                    upstream_keys=(),
                    local_hash="local_b",
                ),
                MODEL_C: GraphIdentityNode(
                    key=MODEL_C,
                    resource_kind=GraphResourceKind.MODEL,
                    upstream_keys=(),
                    local_hash=None,
                ),
            },
            execution_order=(MODEL_B, MODEL_C, MODEL_A),
            expected_hashes={
                MODEL_A: "local_a|model:b=local_b",
                MODEL_B: "local_b",
                MODEL_C: None,
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_identity_graph_when_building_expected_hashes_then_resolves_from_upstreams(
    test_case: GraphIdentityExpectedHashesTestCase,
) -> None:
    result: dict[GraphNodeKey, str | None] = build_expected_graph_identity_hashes(
        nodes=test_case.nodes,
        execution_order=test_case.execution_order,
        compose_identity=compose_readable_identity,
    )

    assert result == test_case.expected_hashes


@pytest.mark.parametrize(
    "test_case",
    [
        GraphIdentityWriteHashesTestCase(
            description="recomputes selected child from caller supplied parent write hash",
            nodes={
                MODEL_A: GraphIdentityNode(
                    key=MODEL_A,
                    resource_kind=GraphResourceKind.MODEL,
                    upstream_keys=(MODEL_B,),
                    local_hash="local_a",
                ),
                MODEL_B: GraphIdentityNode(
                    key=MODEL_B,
                    resource_kind=GraphResourceKind.MODEL,
                    upstream_keys=(),
                    local_hash="local_b",
                ),
            },
            execution_order=(MODEL_B, MODEL_A),
            selected_keys=frozenset({MODEL_A}),
            base_identity_hashes={MODEL_B: "honest_b"},
            expected_hashes={
                MODEL_A: "local_a|model:b=honest_b",
                MODEL_B: "honest_b",
            },
        ),
        GraphIdentityWriteHashesTestCase(
            description="composes a fully selected diamond from the shared root once",
            nodes={
                MODEL_A: GraphIdentityNode(
                    key=MODEL_A,
                    resource_kind=GraphResourceKind.MODEL,
                    upstream_keys=(),
                    local_hash="local_a",
                ),
                MODEL_B: GraphIdentityNode(
                    key=MODEL_B,
                    resource_kind=GraphResourceKind.MODEL,
                    upstream_keys=(MODEL_A,),
                    local_hash="local_b",
                ),
                MODEL_C: GraphIdentityNode(
                    key=MODEL_C,
                    resource_kind=GraphResourceKind.MODEL,
                    upstream_keys=(MODEL_A,),
                    local_hash="local_c",
                ),
                MODEL_D: GraphIdentityNode(
                    key=MODEL_D,
                    resource_kind=GraphResourceKind.MODEL,
                    upstream_keys=(MODEL_B, MODEL_C),
                    local_hash="local_d",
                ),
            },
            execution_order=(MODEL_A, MODEL_B, MODEL_C, MODEL_D),
            selected_keys=frozenset({MODEL_A, MODEL_B, MODEL_C, MODEL_D}),
            base_identity_hashes={},
            expected_hashes={
                MODEL_A: "local_a",
                MODEL_B: "local_b|model:a=local_a",
                MODEL_C: "local_c|model:a=local_a",
                MODEL_D: "local_d|model:b=local_b|model:a=local_a,model:c=local_c|model:a=local_a",
            },
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_available_hashes_when_building_write_hashes_then_uses_caller_supplied_upstreams(
    test_case: GraphIdentityWriteHashesTestCase,
) -> None:
    result: dict[GraphNodeKey, str] = build_graph_write_identity_hashes(
        nodes=test_case.nodes,
        execution_order=test_case.execution_order,
        selected_keys=test_case.selected_keys,
        base_identity_hashes=test_case.base_identity_hashes,
        compose_identity=compose_readable_identity,
    )

    assert result == test_case.expected_hashes


@pytest.mark.parametrize(
    "test_case",
    [
        GraphIdentityWritePerfTestCase(
            description="fully selected densely connected graph resolves without path blowup",
            layer_count=400,
            expected_max_seconds=5.0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_fully_selected_dense_graph_when_building_write_hashes_then_stays_linear(
    test_case: GraphIdentityWritePerfTestCase,
) -> None:
    nodes: dict[GraphNodeKey, GraphIdentityNode]
    execution_order: tuple[GraphNodeKey, ...]
    nodes, execution_order = build_diamond_ladder_identity_nodes(layer_count=test_case.layer_count)

    start: float = time.monotonic()
    result: dict[GraphNodeKey, str] = build_graph_write_identity_hashes(
        nodes=nodes,
        execution_order=execution_order,
        selected_keys=frozenset(nodes.keys()),
        base_identity_hashes={},
        compose_identity=compose_hashed_identity,
    )
    elapsed: float = time.monotonic() - start

    assert len(result) == len(nodes)
    assert elapsed < test_case.expected_max_seconds
