"""Tests for lifecycle-aware run classification."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.python_nodes.helpers.run_lifecycle import (
    build_python_sql_run_lifecycle_plan,
)
from sqlbuild.compiler.python_nodes.models import (
    PythonNodeGraph,
    PythonSqlRunLifecyclePlan,
    PythonSqlRunSelection,
)
from tests.unit.src.sqlbuild.compiler.python_nodes.helpers._test_types import (
    PythonSqlRunLifecycleTestCase,
)
from tests.unit.src.sqlbuild.compiler.python_nodes.helpers.helpers import (
    build_python_node_graph_for_case,
)

RUN_LIFECYCLE_TEST_CASES: list[PythonSqlRunLifecycleTestCase] = [
    PythonSqlRunLifecycleTestCase(
        description="classifies loader upstream task into pre sql ingress",
        python_graph_case="orders",
        selection=PythonSqlRunSelection(
            sql_keys=frozenset(
                {CompiledObjectKey(resource_type=CompiledResourceType.SOURCE, name="raw_orders")}
            ),
            python_node_names=frozenset({"prepare_orders", "load_events"}),
        ),
        expected_region_1_python_names=frozenset({"prepare_orders", "load_events"}),
        expected_region_1_loader_names=frozenset({"load_events"}),
        expected_region_2_python_names=frozenset(),
        expected_region_2_sql_names=frozenset({"raw_orders"}),
    ),
    PythonSqlRunLifecycleTestCase(
        description="classifies read only asset into sql python region",
        python_graph_case="orders",
        selection=PythonSqlRunSelection(
            sql_keys=frozenset(
                {CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="orders")}
            ),
            python_node_names=frozenset({"export_orders"}),
        ),
        expected_region_1_python_names=frozenset(),
        expected_region_1_loader_names=frozenset(),
        expected_region_2_python_names=frozenset({"export_orders"}),
        expected_region_2_sql_names=frozenset({"orders"}),
    ),
    PythonSqlRunLifecycleTestCase(
        description="classifies intermediate loader dependency into pre sql ingress",
        python_graph_case="intermediate_loader_asset_dependency",
        selection=PythonSqlRunSelection(
            sql_keys=frozenset(
                {CompiledObjectKey(resource_type=CompiledResourceType.SOURCE, name="fetch_pages")}
            ),
            python_node_names=frozenset({"fetch_pages", "export_orders"}),
        ),
        expected_region_1_python_names=frozenset({"fetch_pages"}),
        expected_region_1_loader_names=frozenset({"fetch_pages"}),
        expected_region_2_python_names=frozenset({"export_orders"}),
        expected_region_2_sql_names=frozenset({"fetch_pages"}),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    RUN_LIFECYCLE_TEST_CASES,
    ids=[case.description for case in RUN_LIFECYCLE_TEST_CASES],
)
def test_given_run_selection_when_building_lifecycle_plan_then_classifies_regions(
    test_case: PythonSqlRunLifecycleTestCase,
) -> None:
    graph: PythonNodeGraph = build_python_node_graph_for_case(test_case.python_graph_case)

    result: PythonSqlRunLifecyclePlan = build_python_sql_run_lifecycle_plan(
        selection=test_case.selection,
        python_graph=graph,
    )

    assert result.region_1_python_node_names == test_case.expected_region_1_python_names
    assert result.region_1_loader_names == test_case.expected_region_1_loader_names
    assert result.region_2_python_node_names == test_case.expected_region_2_python_names
    assert frozenset(key.name for key in result.region_2_sql_keys) == (
        test_case.expected_region_2_sql_names
    )
