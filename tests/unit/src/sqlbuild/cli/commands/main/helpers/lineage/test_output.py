from __future__ import annotations

from collections.abc import Callable

import pytest

from sqlbuild.cli.commands.main.helpers.lineage.models import ColumnLineageTrace, LineageGraph
from sqlbuild.cli.commands.main.helpers.lineage.output import (
    format_column_lineage_json,
    format_column_lineage_list,
    format_column_lineage_tree,
    format_lineage_list,
    format_lineage_tree,
)
from sqlbuild.cli.commands.main.helpers.lineage.selection import select_target_lineage
from sqlbuild.compiler.pipeline.models import ProjectGraph
from tests.unit.src.sqlbuild.cli.commands.main.helpers.lineage._test_types import (
    ColumnLineageOutputTestCase,
    LargeColumnLineageOutputTestCase,
    LineageOutputTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.helpers.lineage.helpers import (
    build_column_lineage_trace,
    build_large_column_lineage_trace,
    build_lineage_test_graph,
)

LINEAGE_OUTPUT_TEST_CASES: list[LineageOutputTestCase] = [
    LineageOutputTestCase(
        description="renders tree output with branch glyphs and metadata",
        output_format="tree",
        expected_output=(
            "Lineage  model  fact_orders  models/fact_orders.sql  upstream\n"
            "├── model  stg_orders  models/stg_orders.sql\n"
            "│   └── source  raw_orders  sources/raw.yml\n"
            "└── seed  waffle_types  seeds/waffle_types.csv"
        ),
    ),
    LineageOutputTestCase(
        description="renders list output as aligned edge list",
        output_format="list",
        expected_output=(
            "model:stg_orders  -> model:fact_orders\n"
            "seed:waffle_types -> model:fact_orders\n"
            "source:raw_orders -> model:stg_orders"
        ),
    ),
]

COLUMN_LINEAGE_OUTPUT_TEST_CASES: list[ColumnLineageOutputTestCase] = [
    ColumnLineageOutputTestCase(
        description="renders column tree output with end-user dependency labels",
        output_format="tree",
        expected_output=(
            "Column trace  fact_orders.line_total_cents  upstream\n\n"
            "  <- stg_orders.quantity (expression)\n"
            "  <- wide_model_1.line_total_cents (from SELECT *)"
        ),
    ),
    ColumnLineageOutputTestCase(
        description="renders column list output as dependency list",
        output_format="list",
        expected_output=(
            "Column dependencies\n\n"
            "stg_orders.quantity           -> fact_orders.line_total_cents expression\n"
            "wide_model_1.line_total_cents -> fact_orders.line_total_cents from SELECT *"
        ),
    ),
    ColumnLineageOutputTestCase(
        description="renders column json output with graph terms for machines",
        output_format="json",
        expected_output=(
            '{\n  "target": {\n    "resource_type": "model",\n'
            '    "resource_name": "fact_orders",\n'
            '    "column_name": "line_total_cents"\n  },\n'
            '  "direction": "upstream",\n  "trace": [\n    {\n'
            '      "source": {\n        "resource_type": "model",\n'
            '        "resource_name": "stg_orders",\n'
            '        "column_name": "quantity"\n      },\n'
            '      "target": {\n        "resource_type": "model",\n'
            '        "resource_name": "fact_orders",\n'
            '        "column_name": "line_total_cents"\n      },\n'
            '      "transform": "expression",\n'
            '      "confidence": "high"\n    },\n    {\n'
            '      "source": {\n        "resource_type": "model",\n'
            '        "resource_name": "wide_model_1",\n'
            '        "column_name": "line_total_cents"\n      },\n'
            '      "target": {\n        "resource_type": "model",\n'
            '        "resource_name": "fact_orders",\n'
            '        "column_name": "line_total_cents"\n      },\n'
            '      "transform": "star",\n'
            '      "confidence": "medium"\n    }\n  ]\n}'
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    LINEAGE_OUTPUT_TEST_CASES,
    ids=[case.description for case in LINEAGE_OUTPUT_TEST_CASES],
)
def test_given_lineage_graph_when_formatting_then_returns_expected_human_output(
    test_case: LineageOutputTestCase,
) -> None:
    graph: ProjectGraph = build_lineage_test_graph()
    lineage_graph: LineageGraph = select_target_lineage(
        graph=graph,
        target="fact_orders",
        direction="upstream",
        depth=None,
    )

    renderers: dict[str, Callable[[LineageGraph], str]] = {
        "tree": lambda graph: format_lineage_tree(graph, use_color=False),
        "list": lambda graph: format_lineage_list(graph, use_color=False),
    }
    result: str = renderers[test_case.output_format](lineage_graph)

    assert result == test_case.expected_output


@pytest.mark.parametrize(
    "test_case",
    COLUMN_LINEAGE_OUTPUT_TEST_CASES,
    ids=[case.description for case in COLUMN_LINEAGE_OUTPUT_TEST_CASES],
)
def test_given_column_lineage_trace_when_formatting_then_returns_expected_output(
    test_case: ColumnLineageOutputTestCase,
) -> None:
    trace: ColumnLineageTrace = build_column_lineage_trace()
    renderers: dict[str, Callable[[ColumnLineageTrace], str]] = {
        "tree": lambda trace: format_column_lineage_tree(trace, use_color=False),
        "list": lambda trace: format_column_lineage_list(trace, use_color=False),
        "json": format_column_lineage_json,
    }

    result: str = renderers[test_case.output_format](trace)

    assert result == test_case.expected_output


@pytest.mark.parametrize(
    "test_case",
    [
        LargeColumnLineageOutputTestCase(
            description="limits large human column traces",
            expected_included_fragment="consumer_24.order_id",
            expected_excluded_fragment="consumer_25.order_id",
            expected_summary_fragment="Showing 25 of 30 columns.",
            expected_json_tip_fragment="Use --format json for the full trace.",
        )
    ],
    ids=["limits large human column traces"],
)
def test_given_large_column_trace_when_formatting_tree_then_limits_human_output(
    test_case: LargeColumnLineageOutputTestCase,
) -> None:
    trace: ColumnLineageTrace = build_large_column_lineage_trace()

    result: str = format_column_lineage_tree(trace, use_color=False)

    assert test_case.expected_included_fragment in result
    assert test_case.expected_excluded_fragment not in result
    assert test_case.expected_summary_fragment in result
    assert test_case.expected_json_tip_fragment in result
