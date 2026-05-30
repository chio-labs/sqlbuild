"""Tests for executable Python-node selector helpers."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.planner.main.selector_parse import parse_project_selector
from sqlbuild.compiler.planner.models import ParsedSelector
from sqlbuild.compiler.planner.types import SelectorKind
from sqlbuild.compiler.python_nodes.helpers.selectors import resolve_python_node_selectors
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph
from tests.unit.src.sqlbuild.compiler.python_nodes.helpers._test_types import (
    PythonNodeParseSelectorTestCase,
    PythonNodeSelectorErrorTestCase,
    PythonNodeSelectorTestCase,
)
from tests.unit.src.sqlbuild.compiler.python_nodes.helpers.helpers import (
    build_orders_python_node_graph,
)

PYTHON_NODE_PARSE_SELECTOR_TEST_CASES: list[PythonNodeParseSelectorTestCase] = [
    PythonNodeParseSelectorTestCase(
        description="parses task typed selector",
        raw="task:prepare_orders",
        expected_result=ParsedSelector(kind=SelectorKind.TASK, value="prepare_orders"),
    ),
    PythonNodeParseSelectorTestCase(
        description="parses asset typed selector",
        raw="asset:export_orders",
        expected_result=ParsedSelector(kind=SelectorKind.ASSET, value="export_orders"),
    ),
    PythonNodeParseSelectorTestCase(
        description="parses loader typed selector",
        raw="loader:load_events",
        expected_result=ParsedSelector(kind=SelectorKind.LOADER, value="load_events"),
    ),
    PythonNodeParseSelectorTestCase(
        description="parses check typed selector",
        raw="check:check_orders_export",
        expected_result=ParsedSelector(
            kind=SelectorKind.CHECK,
            value="check_orders_export",
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    PYTHON_NODE_PARSE_SELECTOR_TEST_CASES,
    ids=[case.description for case in PYTHON_NODE_PARSE_SELECTOR_TEST_CASES],
)
def test_given_python_node_typed_selector_when_parsing_then_returns_expected_kind(
    test_case: PythonNodeParseSelectorTestCase,
) -> None:
    result: object = parse_project_selector(test_case.raw)

    assert result == test_case.expected_result


PYTHON_NODE_SELECTOR_TEST_CASES: list[PythonNodeSelectorTestCase] = [
    PythonNodeSelectorTestCase(
        description="selects Python node by bare name",
        select=("prepare_orders",),
        exclude=(),
        expected_names=frozenset({"prepare_orders"}),
    ),
    PythonNodeSelectorTestCase(
        description="selects Python node by typed selector",
        select=("asset:export_orders",),
        exclude=(),
        expected_names=frozenset({"export_orders"}),
    ),
    PythonNodeSelectorTestCase(
        description="selects upstream Python nodes with leading plus",
        select=("+check_orders_export",),
        exclude=(),
        expected_names=frozenset({"prepare_orders", "export_orders", "check_orders_export"}),
    ),
    PythonNodeSelectorTestCase(
        description="selects downstream Python nodes with trailing plus",
        select=("prepare_orders+",),
        exclude=(),
        expected_names=frozenset(
            {"prepare_orders", "load_events", "export_orders", "check_orders_export"}
        ),
    ),
    PythonNodeSelectorTestCase(
        description="selects Python nodes by tag",
        select=("tag:daily",),
        exclude=(),
        expected_names=frozenset({"prepare_orders", "export_orders"}),
    ),
    PythonNodeSelectorTestCase(
        description="selects tagged Python nodes with downstream expansion",
        select=("tag:exports+",),
        exclude=(),
        expected_names=frozenset({"export_orders", "check_orders_export"}),
    ),
    PythonNodeSelectorTestCase(
        description="intersects comma-separated Python-node selectors",
        select=("tag:daily,asset:export_orders",),
        exclude=(),
        expected_names=frozenset({"export_orders"}),
    ),
    PythonNodeSelectorTestCase(
        description="excludes Python nodes after expansion",
        select=("prepare_orders+",),
        exclude=("check:check_orders_export",),
        expected_names=frozenset({"prepare_orders", "load_events", "export_orders"}),
    ),
    PythonNodeSelectorTestCase(
        description="returns all Python nodes when select is empty",
        select=(),
        exclude=(),
        expected_names=frozenset(
            {"load_events", "prepare_orders", "export_orders", "check_orders_export"}
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    PYTHON_NODE_SELECTOR_TEST_CASES,
    ids=[case.description for case in PYTHON_NODE_SELECTOR_TEST_CASES],
)
def test_given_python_node_selectors_when_resolving_then_returns_expected_names(
    test_case: PythonNodeSelectorTestCase,
) -> None:
    graph: PythonNodeGraph = build_orders_python_node_graph()

    result: frozenset[str] = resolve_python_node_selectors(
        select=test_case.select,
        exclude=test_case.exclude,
        graph=graph,
    )

    assert result == test_case.expected_names


PYTHON_NODE_SELECTOR_ERROR_TEST_CASES: list[PythonNodeSelectorErrorTestCase] = [
    PythonNodeSelectorErrorTestCase(
        description="raises when typed selector has wrong Python node kind",
        select=("task:export_orders",),
        exclude=(),
        expected_error_type=ValueError,
        expected_error_fragment="unknown Python node selector 'export_orders'",
    ),
    PythonNodeSelectorErrorTestCase(
        description="raises when tag selector matches no Python nodes",
        select=("tag:missing",),
        exclude=(),
        expected_error_type=ValueError,
        expected_error_fragment="no Python nodes found with tag 'missing'",
    ),
    PythonNodeSelectorErrorTestCase(
        description="raises when SQL source selector is used for Python nodes",
        select=("source:raw_orders",),
        exclude=(),
        expected_error_type=ValueError,
        expected_error_fragment="does not map to a Python node type",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    PYTHON_NODE_SELECTOR_ERROR_TEST_CASES,
    ids=[case.description for case in PYTHON_NODE_SELECTOR_ERROR_TEST_CASES],
)
def test_given_invalid_python_node_selector_when_resolving_then_raises_clear_error(
    test_case: PythonNodeSelectorErrorTestCase,
) -> None:
    graph: PythonNodeGraph = build_orders_python_node_graph()

    with pytest.raises(test_case.expected_error_type, match=test_case.expected_error_fragment):
        resolve_python_node_selectors(
            select=test_case.select,
            exclude=test_case.exclude,
            graph=graph,
        )
