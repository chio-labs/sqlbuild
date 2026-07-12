import pytest

from sqlbuild.compiler.planner.main.planning.resolve_clone_boundary import (
    resolve_clone_boundary,
)
from sqlbuild.compiler.planner.main.planning.resolve_skipped_view_chain import (
    resolve_skipped_view_chain,
)
from tests.unit.src.sqlbuild.compiler.planner.main._test_types import (
    CloneBoundaryTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
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
    ],
    ids=lambda case: case.description,
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
