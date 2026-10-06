from __future__ import annotations

from typing import cast

import pytest

from sqlbuild.cli.commands._helpers.lineage.selection import (
    normalize_lineage_target,
    select_column_target_lineage,
    select_selector_lineage,
    select_target_lineage,
)
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cli.commands.models import ColumnLineageTrace, LineageGraph
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.lineage.models import (
    ColumnLineageEdge,
    ProjectColumnLineage,
    QualifiedLineageColumn,
)
from sqlbuild.compiler.lineage.types import ColumnLineageMode
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.main.selection.selection import resolve_project_selectors
from tests.unit.src.sqlbuild.cli.commands._helpers.lineage._test_types import (
    ColumnLineageSelectionTestCase,
    LineagePathSelectorErrorTestCase,
    LineagePathSelectorTestCase,
    LineageSelectionTestCase,
    LineageSelectorDepthErrorTestCase,
    NormalizeLineageTargetErrorTestCase,
    NormalizeLineageTargetTestCase,
    SharedSelectorDepthTestCase,
    SharedSelectorErrorParityTestCase,
    SharedSelectorParityTestCase,
)
from tests.unit.src.sqlbuild.cli.commands._helpers.lineage.helpers import (
    build_lineage_test_graph,
    edge_ids,
    node_ids,
)


@pytest.mark.parametrize(
    "test_case",
    [
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
    ],
    ids=lambda case: case.description,
)
def test_given_target_lineage_request_when_selecting_then_returns_expected_subgraph(
    test_case: LineageSelectionTestCase,
) -> None:
    graph: ProjectGraph = build_lineage_test_graph()

    result: LineageGraph = select_target_lineage(
        graph=graph,
        targets=(test_case.target,),
        direction=test_case.direction,
        depth=test_case.depth,
    )

    assert node_ids(result.nodes) == test_case.expected_node_ids
    assert edge_ids(result.edges) == test_case.expected_edge_ids


@pytest.mark.parametrize(
    "test_case",
    [
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
    ],
    ids=lambda case: case.description,
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
        "sqlbuild.cli.commands._helpers.lineage.selection.build_project_column_lineage",
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
    ids=lambda case: case.description,
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
    ids=lambda case: case.description,
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


@pytest.mark.parametrize(
    "test_case",
    [
        LineagePathSelectorTestCase(
            description="keeps only nodes on paths between endpoints",
            select=("raw_orders~daily_rollup",),
            expected_node_ids=(
                "model:daily_rollup",
                "model:fact_orders",
                "model:stg_orders",
                "source:raw_orders",
            ),
        ),
        LineagePathSelectorTestCase(
            description="adds upstreams of the path start",
            select=("+stg_orders~daily_rollup",),
            expected_node_ids=(
                "model:daily_rollup",
                "model:fact_orders",
                "model:stg_orders",
                "source:raw_orders",
            ),
        ),
        LineagePathSelectorTestCase(
            description="adds downstreams of the path end",
            select=("raw_orders~stg_orders+",),
            expected_node_ids=(
                "model:daily_rollup",
                "model:fact_orders",
                "model:stg_orders",
                "source:raw_orders",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_path_selector_when_selecting_lineage_then_returns_path_nodes(
    test_case: LineagePathSelectorTestCase,
) -> None:
    graph: ProjectGraph = build_lineage_test_graph()

    result: LineageGraph = select_selector_lineage(
        graph=graph,
        select=test_case.select,
        exclude=(),
        depth=None,
    )

    assert node_ids(result.nodes) == test_case.expected_node_ids


@pytest.mark.parametrize(
    "test_case",
    [
        LineagePathSelectorErrorTestCase(
            description="rejects an end that is not downstream of the start",
            select=("daily_rollup~raw_orders",),
            expected_error_fragment=(
                "'source:raw_orders' is not downstream of 'model:daily_rollup'"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unreachable_path_selector_when_selecting_lineage_then_raises_user_error(
    test_case: LineagePathSelectorErrorTestCase,
) -> None:
    graph: ProjectGraph = build_lineage_test_graph()

    with pytest.raises(PlannerInputError) as error:
        select_selector_lineage(
            graph=graph,
            select=test_case.select,
            exclude=(),
            depth=None,
        )

    assert test_case.expected_error_fragment in str(error.value)


@pytest.mark.parametrize(
    "test_case",
    [
        NormalizeLineageTargetTestCase(
            description="bare model is unchanged",
            target="stg_orders",
            expected_target="stg_orders",
        ),
        NormalizeLineageTargetTestCase(
            description="model prefix is stripped",
            target="model:stg_orders",
            expected_target="stg_orders",
        ),
        NormalizeLineageTargetTestCase(
            description="model prefix on a column keeps the column",
            target="model:stg_orders.amount",
            expected_target="stg_orders.amount",
        ),
        NormalizeLineageTargetTestCase(
            description="column prefix is stripped",
            target="column:stg_orders.amount",
            expected_target="stg_orders.amount",
        ),
        NormalizeLineageTargetTestCase(
            description="source prefix is stripped",
            target="source:raw_orders",
            expected_target="raw_orders",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_target_when_normalizing_then_strips_matching_kind_prefix(
    test_case: NormalizeLineageTargetTestCase,
) -> None:
    graph: ProjectGraph = build_lineage_test_graph()

    assert (
        normalize_lineage_target(graph=graph, target=test_case.target) == test_case.expected_target
    )


@pytest.mark.parametrize(
    "test_case",
    [
        NormalizeLineageTargetErrorTestCase(
            description="prefix naming another kind is unknown",
            target="source:stg_orders",
            expected_code="C305",
        ),
        NormalizeLineageTargetErrorTestCase(
            description="column prefix without a column is unknown",
            target="column:stg_orders",
            expected_code="C305",
        ),
        NormalizeLineageTargetErrorTestCase(
            description="column prefix on a source column is unknown",
            target="column:raw_orders.id",
            expected_code="C305",
        ),
        NormalizeLineageTargetErrorTestCase(
            description="prefixed missing model is unknown",
            target="model:missing",
            expected_code="C305",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_mismatched_kind_prefix_when_normalizing_then_raises_unknown_target(
    test_case: NormalizeLineageTargetErrorTestCase,
) -> None:
    graph: ProjectGraph = build_lineage_test_graph()

    with pytest.raises(CliUserError) as raised:
        _ = normalize_lineage_target(graph=graph, target=test_case.target)

    assert raised.value.code == test_case.expected_code


@pytest.mark.parametrize(
    "test_case",
    (
        SharedSelectorParityTestCase(
            description="models-rooted path selects one folder",
            select=("path:models/staging",),
            exclude=(),
            expected_node_ids=("model:stg_orders",),
        ),
        SharedSelectorParityTestCase(
            description="models root selects every model",
            select=("path:models",),
            exclude=(),
            expected_node_ids=("model:daily_rollup", "model:fact_orders", "model:stg_orders"),
        ),
        SharedSelectorParityTestCase(
            description="bare models-rooted path is a path selector",
            select=("models/marts",),
            exclude=(),
            expected_node_ids=("model:daily_rollup", "model:fact_orders"),
        ),
        SharedSelectorParityTestCase(
            description="path selector expands upstream",
            select=("+path:models/staging",),
            exclude=(),
            expected_node_ids=("model:stg_orders", "source:raw_orders"),
        ),
        SharedSelectorParityTestCase(
            description="name glob matches every resource kind",
            select=("*_orders",),
            exclude=(),
            expected_node_ids=("model:fact_orders", "model:stg_orders", "source:raw_orders"),
        ),
        SharedSelectorParityTestCase(
            description="typed glob matches only that kind",
            select=("source:raw_*",),
            exclude=(),
            expected_node_ids=("source:raw_orders",),
        ),
        SharedSelectorParityTestCase(
            description="seed selector expands downstream",
            select=("seed:waffle_types+",),
            exclude=(),
            expected_node_ids=("model:daily_rollup", "model:fact_orders", "seed:waffle_types"),
        ),
        SharedSelectorParityTestCase(
            description="exclude removes a resolved upstream",
            select=("+fact_orders",),
            exclude=("source:raw_orders",),
            expected_node_ids=("model:fact_orders", "model:stg_orders", "seed:waffle_types"),
        ),
        SharedSelectorParityTestCase(
            description="comma intersects tag and path",
            select=("tag:marts,path:models/marts",),
            exclude=(),
            expected_node_ids=("model:daily_rollup", "model:fact_orders"),
        ),
        SharedSelectorParityTestCase(
            description="space-separated selectors are unioned",
            select=("stg_orders daily_rollup",),
            exclude=(),
            expected_node_ids=("model:daily_rollup", "model:stg_orders"),
        ),
        SharedSelectorParityTestCase(
            description="path-between keeps nodes on the path",
            select=("raw_orders~fact_orders",),
            exclude=(),
            expected_node_ids=("model:fact_orders", "model:stg_orders", "source:raw_orders"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_selector_when_selecting_lineage_then_matches_shared_project_selection(
    test_case: SharedSelectorParityTestCase,
) -> None:
    graph: ProjectGraph = build_lineage_test_graph()

    lineage: LineageGraph = select_selector_lineage(
        graph=graph,
        select=test_case.select,
        exclude=test_case.exclude,
        depth=None,
    )
    shared: frozenset[CompiledObjectKey] = resolve_project_selectors(
        select=test_case.select,
        exclude=test_case.exclude,
        all_keys=graph.all_keys,
        upstream_deps=graph.upstream_deps,
        downstream_deps=graph.downstream_deps,
        tag_index=graph.tag_index,
        path_index=graph.path_index,
    )

    assert node_ids(lineage.nodes) == test_case.expected_node_ids
    assert tuple(sorted(f"{key.resource_type}:{key.name}" for key in shared)) == (
        test_case.expected_node_ids
    )


@pytest.mark.parametrize(
    "test_case",
    (
        SharedSelectorErrorParityTestCase(
            description="path without models root is rejected",
            select=("path:staging",),
            expected_code="S012",
        ),
        SharedSelectorErrorParityTestCase(
            description="unknown models-rooted path is rejected",
            select=("path:models/missing",),
            expected_code="S009",
        ),
        SharedSelectorErrorParityTestCase(
            description="unknown tag is rejected",
            select=("tag:missing",),
            expected_code="S008",
        ),
        SharedSelectorErrorParityTestCase(
            description="unknown name is rejected",
            select=("missing_model",),
            expected_code="S007",
        ),
        SharedSelectorErrorParityTestCase(
            description="unsupported selector kind is rejected",
            select=("model:fact_orders",),
            expected_code="S005",
        ),
        SharedSelectorErrorParityTestCase(
            description="inner plus marker is rejected",
            select=("stg+orders",),
            expected_code="S002",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_invalid_selector_when_selecting_lineage_then_raises_shared_selector_error(
    test_case: SharedSelectorErrorParityTestCase,
) -> None:
    graph: ProjectGraph = build_lineage_test_graph()

    with pytest.raises(PlannerInputError) as lineage_error:
        _ = select_selector_lineage(graph=graph, select=test_case.select, exclude=(), depth=None)
    with pytest.raises(PlannerInputError) as shared_error:
        _ = resolve_project_selectors(
            select=test_case.select,
            exclude=(),
            all_keys=graph.all_keys,
            upstream_deps=graph.upstream_deps,
            downstream_deps=graph.downstream_deps,
            tag_index=graph.tag_index,
            path_index=graph.path_index,
        )

    assert lineage_error.value.code == test_case.expected_code
    assert shared_error.value.code == test_case.expected_code
    assert str(lineage_error.value) == str(shared_error.value)


@pytest.mark.parametrize(
    "test_case",
    [
        SharedSelectorDepthTestCase(
            description="glob anchors every match when trimming to depth",
            select=("*_orders+",),
            direction=None,
            expected_node_ids=(
                "model:daily_rollup",
                "model:fact_orders",
                "model:stg_orders",
                "source:raw_orders",
            ),
        ),
        SharedSelectorDepthTestCase(
            description="models-rooted path expands by direction",
            select=("path:models/staging",),
            direction="downstream",
            expected_node_ids=("model:fact_orders", "model:stg_orders"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_shared_selector_with_depth_when_selecting_lineage_then_trims_from_matches(
    test_case: SharedSelectorDepthTestCase,
) -> None:
    graph: ProjectGraph = build_lineage_test_graph()

    result: LineageGraph = select_selector_lineage(
        graph=graph,
        select=test_case.select,
        exclude=(),
        depth=1,
        direction=test_case.direction,
    )

    assert node_ids(result.nodes) == test_case.expected_node_ids
