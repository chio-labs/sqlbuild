from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

import pytest

from sqlbuild.integrations.dbt.helpers.lineage.output import (
    format_dbt_lineage_json,
    format_dbt_lineage_list,
    format_dbt_lineage_tree,
)
from sqlbuild.integrations.dbt.models import DbtLineageGraph
from sqlbuild.integrations.dbt.types import DbtLineageOutputFormat
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtLineageJsonOutputTestCase,
    DbtLineageOutputTestCase,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import (
    build_depth_zero_lineage_graph_for_output_test,
    build_lineage_graph_for_output_test,
)

LINEAGE_OUTPUT_TEST_CASES: tuple[DbtLineageOutputTestCase, ...] = (
    DbtLineageOutputTestCase(
        description="formats list output",
        output_format=DbtLineageOutputFormat.LIST,
        expected_fragments=(
            "stg_orders [dbt]",
            "int_orders [dbt]",
            "fact_orders [sqb]",
            "->",
        ),
    ),
    DbtLineageOutputTestCase(
        description="formats tree output",
        output_format=DbtLineageOutputFormat.TREE,
        expected_fragments=(
            "Lineage",
            "fact_orders [sqb]",
            "int_orders [dbt]",
            "stg_orders [dbt]",
            "└── ",
        ),
    ),
)

LINEAGE_SINGLE_NODE_OUTPUT_TEST_CASES: tuple[DbtLineageOutputTestCase, ...] = (
    DbtLineageOutputTestCase(
        description="formats single node list output",
        output_format=DbtLineageOutputFormat.LIST,
        expected_fragments=("mart_orders [sqb]",),
    ),
    DbtLineageOutputTestCase(
        description="formats single node tree output",
        output_format=DbtLineageOutputFormat.TREE,
        expected_fragments=("Lineage", "mart_orders [sqb]", "upstream"),
    ),
)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtLineageJsonOutputTestCase(
            description="includes node metadata",
            expected_node_metadata=(
                ("dbt:model:model.analytics.int_orders", "label", "int_orders"),
                (
                    "dbt:model:model.analytics.int_orders",
                    "qualified_name",
                    "analytics.int_orders",
                ),
                ("sqb:model:fact_orders", "relative_path", "models/fact_orders.sql"),
            ),
            expected_direction="upstream",
        )
    ],
    ids=["includes node metadata"],
)
def test_given_lineage_graph_when_formatting_json_then_includes_node_metadata(
    test_case: DbtLineageJsonOutputTestCase,
) -> None:
    graph: DbtLineageGraph = build_lineage_graph_for_output_test()

    payload: object = json.loads(format_dbt_lineage_json(graph))

    assert isinstance(payload, dict)
    nodes: object = payload["nodes"]
    assert isinstance(nodes, list)
    node_by_id: dict[str, Mapping[str, object]] = {
        str(cast(Mapping[str, object], node)["id"]): cast(Mapping[str, object], node)
        for node in nodes
        if isinstance(node, dict)
    }
    for node_id, metadata_key, expected_value in test_case.expected_node_metadata:
        assert node_by_id[node_id][metadata_key] == expected_value
    assert payload["direction"] == test_case.expected_direction


@pytest.mark.parametrize(
    "test_case",
    LINEAGE_OUTPUT_TEST_CASES,
    ids=[case.description for case in LINEAGE_OUTPUT_TEST_CASES],
)
def test_given_lineage_graph_when_formatting_human_output_then_includes_expected_fragments(
    test_case: DbtLineageOutputTestCase,
) -> None:
    graph: DbtLineageGraph = build_lineage_graph_for_output_test()

    output: str = (
        format_dbt_lineage_list(graph, use_color=False)
        if test_case.output_format == DbtLineageOutputFormat.LIST
        else format_dbt_lineage_tree(graph, use_color=False)
    )

    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in output


@pytest.mark.parametrize(
    "test_case",
    LINEAGE_SINGLE_NODE_OUTPUT_TEST_CASES,
    ids=[case.description for case in LINEAGE_SINGLE_NODE_OUTPUT_TEST_CASES],
)
def test_given_single_node_lineage_graph_when_formatting_human_output_then_includes_focus_node(
    test_case: DbtLineageOutputTestCase,
) -> None:
    graph: DbtLineageGraph = build_depth_zero_lineage_graph_for_output_test()

    output: str = (
        format_dbt_lineage_list(graph, use_color=False)
        if test_case.output_format == DbtLineageOutputFormat.LIST
        else format_dbt_lineage_tree(graph, use_color=False)
    )

    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in output


@pytest.mark.parametrize(
    "test_case",
    [
        DbtLineageOutputTestCase(
            description="formats summary fallback without focus",
            output_format=DbtLineageOutputFormat.TREE,
            expected_fragments=("Lineage graph", "mart_orders [sqb]"),
        )
    ],
    ids=["formats summary fallback without focus"],
)
def test_given_lineage_graph_without_focus_when_formatting_tree_then_outputs_summary(
    test_case: DbtLineageOutputTestCase,
) -> None:
    graph: DbtLineageGraph = build_depth_zero_lineage_graph_for_output_test()
    summary_graph: DbtLineageGraph = DbtLineageGraph(nodes=graph.nodes, edges=graph.edges)

    output: str = format_dbt_lineage_tree(summary_graph, use_color=False)

    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in output
