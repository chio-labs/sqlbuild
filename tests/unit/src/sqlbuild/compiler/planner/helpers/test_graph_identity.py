from __future__ import annotations

import pytest

from sqlbuild.compiler.planner.main.graph_identity import (
    build_expected_graph_identity_hashes,
)
from sqlbuild.compiler.planner.main.graph_write_identity import build_graph_write_identity_hashes
from sqlbuild.compiler.planner.models import GraphIdentityNode, GraphNodeKey
from sqlbuild.compiler.planner.types import GraphResourceKind
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
    GraphIdentityExpectedHashesTestCase,
    GraphIdentityWriteHashesTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers.helpers import compose_readable_identity

MODEL_A: GraphNodeKey = GraphNodeKey(node_type="model", node_name="a")
MODEL_B: GraphNodeKey = GraphNodeKey(node_type="model", node_name="b")
MODEL_C: GraphNodeKey = GraphNodeKey(node_type="model", node_name="c")


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
    ids=["uses dependency order and named upstream keys while preserving missing nodes"],
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
        )
    ],
    ids=["recomputes selected child from caller supplied parent write hash"],
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
