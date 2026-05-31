"""Tests for run-command SQL/Python selector helpers."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.python_nodes.helpers.run_selectors import resolve_python_sql_run_selectors
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph, PythonSqlRunSelection
from tests.unit.src.sqlbuild.compiler.python_nodes.helpers._test_types import (
    PythonSqlSelectorErrorTestCase,
    PythonSqlSelectorTestCase,
)
from tests.unit.src.sqlbuild.compiler.python_nodes.helpers.helpers import (
    build_orders_project_graph,
    build_orders_python_node_graph,
)

PYTHON_SQL_RUN_SELECTOR_TEST_CASES: list[PythonSqlSelectorTestCase] = [
    PythonSqlSelectorTestCase(
        description="selects task and asset nodes but excludes checks by default",
        select=(),
        exclude=(),
        expected_sql_names=frozenset({"raw_orders", "orders"}),
        expected_python_node_names=frozenset({"load_events", "prepare_orders", "export_orders"}),
    ),
    PythonSqlSelectorTestCase(
        description="selects explicit Python asset path for run",
        select=("path:assets",),
        exclude=(),
        expected_sql_names=frozenset(),
        expected_python_node_names=frozenset({"prepare_orders", "export_orders"}),
    ),
    PythonSqlSelectorTestCase(
        description="preserves source terminal loader requirement for run",
        select=("source:raw_orders",),
        exclude=(),
        expected_sql_names=frozenset({"raw_orders"}),
        expected_python_node_names=frozenset({"prepare_orders", "load_events"}),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    PYTHON_SQL_RUN_SELECTOR_TEST_CASES,
    ids=[case.description for case in PYTHON_SQL_RUN_SELECTOR_TEST_CASES],
)
def test_given_run_selectors_when_resolving_then_excludes_python_checks(
    test_case: PythonSqlSelectorTestCase,
) -> None:
    project_graph: ProjectGraph = build_orders_project_graph()
    python_graph: PythonNodeGraph = build_orders_python_node_graph()

    result: PythonSqlRunSelection = resolve_python_sql_run_selectors(
        select=test_case.select,
        exclude=test_case.exclude,
        project_graph=project_graph,
        python_graph=python_graph,
    )

    assert frozenset(key.name for key in result.sql_keys) == test_case.expected_sql_names
    assert result.python_node_names == test_case.expected_python_node_names


PYTHON_SQL_RUN_SELECTOR_ERROR_TEST_CASES: list[PythonSqlSelectorErrorTestCase] = [
    PythonSqlSelectorErrorTestCase(
        description="rejects explicit check selector for run",
        select=("check:check_orders_export",),
        exclude=(),
        expected_error_type=ValueError,
        expected_error_fragment="sqb run does not execute Python checks: check_orders_export",
    ),
    PythonSqlSelectorErrorTestCase(
        description="rejects tag selector that includes a check for run",
        select=("tag:exports",),
        exclude=(),
        expected_error_type=ValueError,
        expected_error_fragment="sqb run does not execute Python checks: check_orders_export",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    PYTHON_SQL_RUN_SELECTOR_ERROR_TEST_CASES,
    ids=[case.description for case in PYTHON_SQL_RUN_SELECTOR_ERROR_TEST_CASES],
)
def test_given_run_selector_selects_check_when_resolving_then_raises(
    test_case: PythonSqlSelectorErrorTestCase,
) -> None:
    project_graph: ProjectGraph = build_orders_project_graph()
    python_graph: PythonNodeGraph = build_orders_python_node_graph()

    with pytest.raises(test_case.expected_error_type, match=test_case.expected_error_fragment):
        resolve_python_sql_run_selectors(
            select=test_case.select,
            exclude=test_case.exclude,
            project_graph=project_graph,
            python_graph=python_graph,
        )
