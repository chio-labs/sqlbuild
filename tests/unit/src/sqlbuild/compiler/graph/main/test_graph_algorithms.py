from __future__ import annotations

import pytest

from sqlbuild.compiler.graph.main.invert_edges import invert_edges
from sqlbuild.compiler.graph.main.path_nodes import path_nodes
from sqlbuild.compiler.graph.main.transitive_closure import transitive_closure
from tests.unit.src.sqlbuild.compiler.graph.main._test_types import (
    InvertEdgesTestCase,
    PathNodesTestCase,
    TransitiveClosureTestCase,
)


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
