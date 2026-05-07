from __future__ import annotations

from typing import cast

import pytest

from sqlbuild.cli.commands.main.helpers.lineage.models import ColumnLineageTrace, LineageGraph
from sqlbuild.cli.commands.main.helpers.lineage.selection import (
    select_column_target_lineage,
    select_selector_lineage,
    select_target_lineage,
)
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.lineage.models import (
    ColumnLineageEdge,
    ProjectColumnLineage,
    QualifiedLineageColumn,
)
from sqlbuild.compiler.lineage.types import ColumnLineageMode
from sqlbuild.compiler.pipeline.models import ProjectGraph
from tests.unit.src.sqlbuild.cli.commands.main.helpers.lineage._test_types import (
    ColumnLineageSelectionTestCase,
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

COLUMN_SELECTION_TEST_CASES: list[ColumnLineageSelectionTestCase] = [
    ColumnLineageSelectionTestCase(
        description="selects upstream column trace for dot target",
        target="fact_orders.order_id",
        direction="upstream",
        depth=None,
        expected_resource_name="fact_orders",
        expected_column_name="order_id",
        expected_trace_ids=("stg_orders.order_id->fact_orders.order_id",),
        expected_analyzed_model_names=("fact_orders", "stg_orders"),
        expected_truncated=False,
    ),
    ColumnLineageSelectionTestCase(
        description="respects zero depth for column target",
        target="fact_orders.order_id",
        direction="upstream",
        depth=0,
        expected_resource_name="fact_orders",
        expected_column_name="order_id",
        expected_trace_ids=(),
        expected_analyzed_model_names=("fact_orders",),
        expected_truncated=True,
    ),
    ColumnLineageSelectionTestCase(
        description="selects downstream candidate models for column target",
        target="fact_orders.order_id",
        direction="downstream",
        depth=1,
        expected_resource_name="fact_orders",
        expected_column_name="order_id",
        expected_trace_ids=("fact_orders.order_id->daily_rollup.order_id",),
        expected_analyzed_model_names=("daily_rollup", "fact_orders"),
        expected_truncated=False,
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
    COLUMN_SELECTION_TEST_CASES,
    ids=[case.description for case in COLUMN_SELECTION_TEST_CASES],
)
def test_given_column_target_when_selecting_then_returns_column_trace(
    test_case: ColumnLineageSelectionTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph: ProjectGraph = build_lineage_test_graph()
    received_model_names: list[frozenset[str]] = []
    received_modes: list[ColumnLineageMode] = []

    def build_column_lineage_spy(*args: object, **kwargs: object) -> ProjectColumnLineage:
        del args
        received_model_names.append(cast(frozenset[str], kwargs["model_names"]))
        received_modes.append(cast(ColumnLineageMode, kwargs["mode"]))
        return ProjectColumnLineage(
            models={},
            edges=(
                ColumnLineageEdge(
                    source=QualifiedLineageColumn(
                        resource_type=CompiledResourceType.MODEL,
                        resource_name="stg_orders",
                        column_name="order_id",
                    ),
                    target=QualifiedLineageColumn(
                        resource_type=CompiledResourceType.MODEL,
                        resource_name="fact_orders",
                        column_name="order_id",
                    ),
                ),
                ColumnLineageEdge(
                    source=QualifiedLineageColumn(
                        resource_type=CompiledResourceType.MODEL,
                        resource_name="fact_orders",
                        column_name="order_id",
                    ),
                    target=QualifiedLineageColumn(
                        resource_type=CompiledResourceType.MODEL,
                        resource_name="daily_rollup",
                        column_name="order_id",
                    ),
                ),
            ),
        )

    monkeypatch.setattr(
        "sqlbuild.cli.commands.main.helpers.lineage.selection.build_project_column_lineage",
        build_column_lineage_spy,
    )

    result: ColumnLineageTrace | None = select_column_target_lineage(
        graph=graph,
        target=test_case.target,
        direction=test_case.direction,
        depth=test_case.depth,
        mode=ColumnLineageMode.FAST,
    )

    assert result is not None
    assert result.target.resource_name == test_case.expected_resource_name
    assert result.target.column_name == test_case.expected_column_name
    assert (
        tuple(
            f"{edge.source.resource_name}.{edge.source.column_name}->{edge.target.resource_name}.{edge.target.column_name}"
            for edge in result.trace
        )
        == test_case.expected_trace_ids
    )
    assert tuple(sorted(received_model_names[0])) == test_case.expected_analyzed_model_names
    assert received_modes == [ColumnLineageMode.FAST]
    assert result.mode == ColumnLineageMode.FAST
    assert result.max_depth == test_case.depth
    assert result.analyzed_model_count == len(test_case.expected_analyzed_model_names)
    assert result.truncated is test_case.expected_truncated


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
