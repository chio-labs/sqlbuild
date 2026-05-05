from __future__ import annotations

from collections.abc import Callable

import pytest

from sqlbuild.cli.commands.main.helpers.lineage.models import LineageGraph
from sqlbuild.cli.commands.main.helpers.lineage.output import (
    format_lineage_list,
    format_lineage_tree,
)
from sqlbuild.cli.commands.main.helpers.lineage.selection import select_target_lineage
from sqlbuild.compiler.pipeline.models import ProjectGraph
from tests.unit.src.sqlbuild.cli.commands.main.helpers.lineage._test_types import (
    LineageOutputTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.helpers.lineage.helpers import (
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
