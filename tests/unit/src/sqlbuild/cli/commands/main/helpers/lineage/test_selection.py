from __future__ import annotations

import pytest

from sqlbuild.cli.commands.main.helpers.lineage.models import LineageGraph
from sqlbuild.cli.commands.main.helpers.lineage.selection import (
    select_selector_lineage,
    select_target_lineage,
)
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.compiler.pipeline.models import ProjectGraph
from tests.unit.src.sqlbuild.cli.commands.main.helpers.lineage._test_types import (
    LineageSelectionTestCase,
    LineageSelectorDepthErrorTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.helpers.lineage.helpers import (
    build_lineage_test_graph,
    edge_ids,
    node_ids,
)

SELECTION_TEST_CASES: list[LineageSelectionTestCase] = [
    LineageSelectionTestCase(
        description="limits downstream target lineage to one hop",
        target="fact_orders",
        direction="downstream",
        depth=1,
        expected_node_ids=("model:daily_rollup", "model:fact_orders"),
        expected_edge_ids=("model:fact_orders->model:daily_rollup",),
    ),
    LineageSelectionTestCase(
        description="keeps full upstream target lineage",
        target="fact_orders",
        direction="upstream",
        depth=None,
        expected_node_ids=(
            "model:fact_orders",
            "model:stg_orders",
            "seed:waffle_types",
            "source:raw_orders",
        ),
        expected_edge_ids=(
            "model:stg_orders->model:fact_orders",
            "seed:waffle_types->model:fact_orders",
            "source:raw_orders->model:stg_orders",
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SELECTION_TEST_CASES,
    ids=[case.description for case in SELECTION_TEST_CASES],
)
def test_given_target_lineage_request_when_selecting_then_returns_expected_subgraph(
    test_case: LineageSelectionTestCase,
) -> None:
    graph: ProjectGraph = build_lineage_test_graph()

    result: LineageGraph = select_target_lineage(
        graph=graph,
        target=test_case.target,
        direction=test_case.direction,
        depth=test_case.depth,
    )

    assert node_ids(result.nodes) == test_case.expected_node_ids
    assert edge_ids(result.edges) == test_case.expected_edge_ids


@pytest.mark.parametrize(
    "test_case",
    [
        LineageSelectionTestCase(
            description="trims expanded name selector to requested depth",
            target="unused",
            direction="unused",
            depth=1,
            expected_node_ids=("model:fact_orders", "model:stg_orders", "seed:waffle_types"),
            expected_edge_ids=(
                "model:stg_orders->model:fact_orders",
                "seed:waffle_types->model:fact_orders",
            ),
        )
    ],
    ids=["trims expanded name selector to requested depth"],
)
def test_given_expanded_selector_with_depth_when_selecting_then_trims_selected_subgraph(
    test_case: LineageSelectionTestCase,
) -> None:
    graph: ProjectGraph = build_lineage_test_graph()

    result: LineageGraph = select_selector_lineage(
        graph=graph,
        select=("+fact_orders",),
        exclude=(),
        depth=test_case.depth,
    )

    assert node_ids(result.nodes) == test_case.expected_node_ids
    assert edge_ids(result.edges) == test_case.expected_edge_ids


@pytest.mark.parametrize(
    "test_case",
    [
        LineageSelectorDepthErrorTestCase(
            description="rejects tag selector with depth",
            select=("tag:marts+",),
            expected_error_fragment=(
                "--depth requires name, source, seed, or path-between selectors"
            ),
        )
    ],
    ids=["rejects tag selector with depth"],
)
def test_given_unclear_selector_anchor_with_depth_when_selecting_then_raises_user_error(
    test_case: LineageSelectorDepthErrorTestCase,
) -> None:
    graph: ProjectGraph = build_lineage_test_graph()

    with pytest.raises(CliUserError) as error:
        select_selector_lineage(
            graph=graph,
            select=test_case.select,
            exclude=(),
            depth=1,
        )

    assert test_case.expected_error_fragment in str(error.value)
