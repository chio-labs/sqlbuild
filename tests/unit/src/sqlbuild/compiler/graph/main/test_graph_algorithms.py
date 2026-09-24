from __future__ import annotations

import pytest

from sqlbuild.compiler.graph.main.invert_edges import invert_edges
from sqlbuild.compiler.graph.main.path_nodes import path_nodes
from sqlbuild.compiler.graph.main.transitive_closure import transitive_closure
from sqlbuild.compiler.graph.main.transitive_closure_many import transitive_closure_many
from tests.unit.src.sqlbuild.compiler.graph.main._test_types import (
    InvertEdgesTestCase,
    PathNodesTestCase,
    TransitiveClosureManyTestCase,
    TransitiveClosureTestCase,
)

_DIAMOND_UPSTREAM: dict[str, tuple[str, ...]] = {
    "orders_report": ("orders_left", "orders_right"),
    "orders_left": ("stg_orders",),
    "orders_right": ("stg_orders",),
    "stg_orders": (),
    "inventory_report": ("stg_inventory",),
    "stg_inventory": (),
}

_SHORTCUT_DOWNSTREAM: dict[str, tuple[str, ...]] = {
    "orders": ("orders_left", "orders_right"),
    "orders_right": ("orders_mid",),
    "orders_mid": ("orders_joined",),
    "orders_left": ("orders_joined",),
    "orders_joined": ("orders_report",),
    "orders_report": (),
}


@pytest.mark.parametrize(
    "test_case",
    [
        InvertEdgesTestCase(
            description="inverts edges and keeps nodes with no downstreams",
            edges={"b": ("a",), "c": ("a",), "a": ()},
            expected_edges={"b": (), "c": (), "a": ("b", "c")},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_edges_when_inverting_then_returns_expected_edges(
    test_case: InvertEdgesTestCase,
) -> None:
    result: dict[str, tuple[str, ...]] = invert_edges(
        edges=test_case.edges,
        sort_key=lambda value: value,
    )

    assert result == test_case.expected_edges


@pytest.mark.parametrize(
    "test_case",
    [
        TransitiveClosureTestCase(
            description="walks all reachable nodes through a chain",
            edges={"c": ("b",), "b": ("a",), "a": ("root",), "root": ()},
            start="c",
            max_depth=None,
            expected_nodes=frozenset({"b", "a", "root"}),
        ),
        TransitiveClosureTestCase(
            description="honors max depth",
            edges={"c": ("b",), "b": ("a",), "a": ("root",), "root": ()},
            start="c",
            max_depth=1,
            expected_nodes=frozenset({"b"}),
        ),
        TransitiveClosureTestCase(
            description="bounds depth by the shortest route",
            edges=_SHORTCUT_DOWNSTREAM,
            start="orders",
            max_depth=3,
            expected_nodes=frozenset(
                {"orders_left", "orders_right", "orders_mid", "orders_joined", "orders_report"}
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_edges_when_finding_transitive_closure_then_returns_expected_nodes(
    test_case: TransitiveClosureTestCase,
) -> None:
    result: frozenset[str] = transitive_closure(
        start=test_case.start,
        edges=test_case.edges,
        max_depth=test_case.max_depth,
    )

    assert result == test_case.expected_nodes


@pytest.mark.parametrize(
    "test_case",
    [
        TransitiveClosureManyTestCase(
            description="excludes a single start",
            edges=_DIAMOND_UPSTREAM,
            starts=("orders_report",),
            include_starts=False,
            expected_nodes=frozenset({"orders_left", "orders_right", "stg_orders"}),
        ),
        TransitiveClosureManyTestCase(
            description="includes a single start",
            edges=_DIAMOND_UPSTREAM,
            starts=("orders_report",),
            include_starts=True,
            expected_nodes=frozenset(
                {"orders_report", "orders_left", "orders_right", "stg_orders"}
            ),
        ),
        TransitiveClosureManyTestCase(
            description="unions disconnected starts",
            edges=_DIAMOND_UPSTREAM,
            starts=("orders_left", "inventory_report"),
            include_starts=False,
            expected_nodes=frozenset({"stg_orders", "stg_inventory"}),
        ),
        TransitiveClosureManyTestCase(
            description="keeps an excluded start reachable from another start",
            edges=_DIAMOND_UPSTREAM,
            starts=("orders_report", "orders_left"),
            include_starts=False,
            expected_nodes=frozenset({"orders_left", "orders_right", "stg_orders"}),
        ),
        TransitiveClosureManyTestCase(
            description="includes starts missing from the edge mapping",
            edges=_DIAMOND_UPSTREAM,
            starts=("customers",),
            include_starts=True,
            expected_nodes=frozenset({"customers"}),
        ),
        TransitiveClosureManyTestCase(
            description="returns nothing without starts",
            edges=_DIAMOND_UPSTREAM,
            starts=(),
            include_starts=True,
            expected_nodes=frozenset(),
        ),
        TransitiveClosureManyTestCase(
            description="terminates on cycles",
            edges={"orders": ("customers",), "customers": ("orders",)},
            starts=("orders",),
            include_starts=False,
            expected_nodes=frozenset({"orders", "customers"}),
        ),
        TransitiveClosureManyTestCase(
            description="returns nothing at zero depth without starts",
            edges=_DIAMOND_UPSTREAM,
            starts=("orders_report",),
            include_starts=False,
            max_depth=0,
            expected_nodes=frozenset(),
        ),
        TransitiveClosureManyTestCase(
            description="returns only starts at zero depth with starts",
            edges=_DIAMOND_UPSTREAM,
            starts=("orders_report",),
            include_starts=True,
            max_depth=0,
            expected_nodes=frozenset({"orders_report"}),
        ),
        TransitiveClosureManyTestCase(
            description="bounds depth from every start",
            edges=_DIAMOND_UPSTREAM,
            starts=("orders_report", "inventory_report"),
            include_starts=False,
            max_depth=1,
            expected_nodes=frozenset({"orders_left", "orders_right", "stg_inventory"}),
        ),
        TransitiveClosureManyTestCase(
            description="bounds multi-start depth by the shortest route",
            edges=_SHORTCUT_DOWNSTREAM,
            starts=("orders", "orders_right"),
            include_starts=False,
            max_depth=3,
            expected_nodes=frozenset(
                {"orders_left", "orders_right", "orders_mid", "orders_joined", "orders_report"}
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_edges_when_finding_multi_start_closure_then_returns_expected_nodes(
    test_case: TransitiveClosureManyTestCase,
) -> None:
    result: frozenset[str] = transitive_closure_many(
        starts=test_case.starts,
        edges=test_case.edges,
        include_starts=test_case.include_starts,
        max_depth=test_case.max_depth,
    )

    assert result == test_case.expected_nodes


@pytest.mark.parametrize(
    "test_case",
    [
        PathNodesTestCase(
            description="returns only nodes on paths between endpoints",
            downstream={
                "raw": ("left", "right", "side"),
                "left": ("joined",),
                "right": ("joined",),
                "side": (),
                "joined": ("final",),
                "final": (),
            },
            start="raw",
            end="final",
            expected_nodes=frozenset({"raw", "left", "right", "joined", "final"}),
        ),
        PathNodesTestCase(
            description="returns none when endpoint is unreachable",
            downstream={"a": ("b",), "b": (), "c": ()},
            start="a",
            end="c",
            expected_nodes=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_downstream_edges_when_finding_path_nodes_then_returns_expected_nodes(
    test_case: PathNodesTestCase,
) -> None:
    result: frozenset[str] | None = path_nodes(
        start=test_case.start,
        end=test_case.end,
        downstream=test_case.downstream,
    )

    assert result == test_case.expected_nodes
