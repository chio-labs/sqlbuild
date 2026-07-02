from __future__ import annotations

import pytest

from sqlbuild.shared.helpers.graph.algorithms import (
    invert_edges,
    path_nodes,
    resolve_clone_boundary,
    resolve_skipped_view_chain,
    transitive_closure,
)
from tests.unit.src.sqlbuild.shared.helpers._test_types import (
    CloneBoundaryTestCase,
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
    ids=["inverts edges and keeps nodes with no downstreams"],
)
def test_given_edges_when_inverting_then_returns_expected_edges(
    test_case: InvertEdgesTestCase,
) -> None:
    result: dict[str, tuple[str, ...]] = invert_edges(
        test_case.edges,
        sort_key=lambda value: value,
    )

    assert result == test_case.expected_edges


TRANSITIVE_CLOSURE_TEST_CASES: list[TransitiveClosureTestCase] = [
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
]


@pytest.mark.parametrize(
    "test_case",
    TRANSITIVE_CLOSURE_TEST_CASES,
    ids=[case.description for case in TRANSITIVE_CLOSURE_TEST_CASES],
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


PATH_NODES_TEST_CASES: list[PathNodesTestCase] = [
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
]


@pytest.mark.parametrize(
    "test_case",
    PATH_NODES_TEST_CASES,
    ids=[case.description for case in PATH_NODES_TEST_CASES],
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


CLONE_BOUNDARY_TEST_CASES: list[CloneBoundaryTestCase] = [
    CloneBoundaryTestCase(
        description="clones first table ancestor and rebuilds skipped view",
        upstream={"selected": ("view",), "view": ("table",), "table": ()},
        selected=frozenset({"selected"}),
        clonable_nodes=frozenset({"view", "table"}),
        view_nodes=frozenset({"view"}),
        expected_boundary_nodes=frozenset({"table"}),
        expected_view_chain_nodes=frozenset({"view"}),
    ),
    CloneBoundaryTestCase(
        description="stops at non-clonable non-view source",
        upstream={"selected": ("source",), "source": ("table",), "table": ()},
        selected=frozenset({"selected"}),
        clonable_nodes=frozenset({"table"}),
        view_nodes=frozenset(),
        expected_boundary_nodes=frozenset(),
        expected_view_chain_nodes=frozenset(),
    ),
    CloneBoundaryTestCase(
        description="walks through selected upstream nodes before finding boundary",
        upstream={"selected": ("middle",), "middle": ("table",), "table": ()},
        selected=frozenset({"selected", "middle"}),
        clonable_nodes=frozenset({"middle", "table"}),
        view_nodes=frozenset(),
        expected_boundary_nodes=frozenset({"table"}),
        expected_view_chain_nodes=frozenset(),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    CLONE_BOUNDARY_TEST_CASES,
    ids=[case.description for case in CLONE_BOUNDARY_TEST_CASES],
)
def test_given_clone_graph_when_resolving_boundary_then_returns_expected_nodes(
    test_case: CloneBoundaryTestCase,
) -> None:
    boundary: frozenset[str] = resolve_clone_boundary(
        selected=test_case.selected,
        upstream=test_case.upstream,
        is_clonable=lambda node: node in test_case.clonable_nodes,
        is_view=lambda node: node in test_case.view_nodes,
    )
    view_chain: frozenset[str] = resolve_skipped_view_chain(
        selected=test_case.selected,
        upstream=test_case.upstream,
        is_clonable=lambda node: node in test_case.clonable_nodes,
        is_view=lambda node: node in test_case.view_nodes,
    )

    assert boundary == test_case.expected_boundary_nodes
    assert view_chain == test_case.expected_view_chain_nodes
