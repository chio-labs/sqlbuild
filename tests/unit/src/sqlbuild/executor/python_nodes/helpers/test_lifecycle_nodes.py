"""Tests for building Python lifecycle scheduler nodes."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.python_nodes.models import PythonNodeGraph, PythonSqlRunLifecyclePlan
from sqlbuild.executor.python_nodes.helpers.lifecycle_nodes import (
    build_region_1_lifecycle_nodes,
    build_region_2_python_lifecycle_nodes,
)
from sqlbuild.executor.shared.models.lifecycle_scheduler import LifecycleExecutionNode
from tests.unit.src.sqlbuild.executor.python_nodes.helpers._test_types import (
    PythonNodeLifecycleNodeBuildTestCase,
)
from tests.unit.src.sqlbuild.executor.python_nodes.helpers.helpers import (
    build_lifecycle_plan_for_selected_python_names,
    lifecycle_node_payload_name,
    python_graph_for_lifecycle_case,
)

REGION_1_LIFECYCLE_NODE_TEST_CASES: list[PythonNodeLifecycleNodeBuildTestCase] = [
    PythonNodeLifecycleNodeBuildTestCase(
        description="builds pre sql task and loader scheduler nodes",
        python_graph_case="orders",
        selected_names=frozenset({"prepare_orders", "load_events"}),
        expected_names=("load_events", "prepare_orders"),
        expected_kinds=("loader", "task"),
        expected_upstream_names=(("prepare_orders",), ()),
        expected_payload_names=("load_events", "prepare_orders"),
    ),
    PythonNodeLifecycleNodeBuildTestCase(
        description="builds intermediate loader scheduler node",
        python_graph_case="intermediate_loader_asset_dependency",
        selected_names=frozenset({"fetch_pages", "export_orders"}),
        expected_names=("fetch_pages",),
        expected_kinds=("loader",),
        expected_upstream_names=((),),
        expected_payload_names=("fetch_pages",),
    ),
]

REGION_2_LIFECYCLE_NODE_TEST_CASES: list[PythonNodeLifecycleNodeBuildTestCase] = [
    PythonNodeLifecycleNodeBuildTestCase(
        description="builds read only asset scheduler node",
        python_graph_case="orders",
        selected_names=frozenset({"export_orders"}),
        expected_names=("export_orders",),
        expected_kinds=("asset",),
        expected_upstream_names=((),),
        expected_payload_names=("export_orders",),
    ),
    PythonNodeLifecycleNodeBuildTestCase(
        description="builds read only task scheduler node",
        python_graph_case="orders",
        selected_names=frozenset({"prepare_orders"}),
        expected_names=("prepare_orders",),
        expected_kinds=("task",),
        expected_upstream_names=((),),
        expected_payload_names=("prepare_orders",),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    REGION_1_LIFECYCLE_NODE_TEST_CASES,
    ids=[case.description for case in REGION_1_LIFECYCLE_NODE_TEST_CASES],
)
def test_given_lifecycle_plan_when_building_region_1_nodes_then_returns_python_scheduler_nodes(
    test_case: PythonNodeLifecycleNodeBuildTestCase,
) -> None:
    graph: PythonNodeGraph = python_graph_for_lifecycle_case(test_case.python_graph_case)
    plan: PythonSqlRunLifecyclePlan = build_lifecycle_plan_for_selected_python_names(
        graph=graph,
        selected_names=test_case.selected_names,
    )

    result: tuple[LifecycleExecutionNode, ...] = build_region_1_lifecycle_nodes(
        plan=plan,
        python_graph=graph,
    )

    assert tuple(node.name for node in result) == test_case.expected_names
    assert tuple(node.kind for node in result) == test_case.expected_kinds
    assert tuple(node.upstream_names for node in result) == test_case.expected_upstream_names
    assert tuple(lifecycle_node_payload_name(node) for node in result) == (
        test_case.expected_payload_names
    )


@pytest.mark.parametrize(
    "test_case",
    REGION_2_LIFECYCLE_NODE_TEST_CASES,
    ids=[case.description for case in REGION_2_LIFECYCLE_NODE_TEST_CASES],
)
def test_given_lifecycle_plan_when_building_region_2_nodes_then_returns_python_scheduler_nodes(
    test_case: PythonNodeLifecycleNodeBuildTestCase,
) -> None:
    graph: PythonNodeGraph = python_graph_for_lifecycle_case(test_case.python_graph_case)
    plan: PythonSqlRunLifecyclePlan = build_lifecycle_plan_for_selected_python_names(
        graph=graph,
        selected_names=test_case.selected_names,
    )

    result: tuple[LifecycleExecutionNode, ...] = build_region_2_python_lifecycle_nodes(
        plan=plan,
        python_graph=graph,
    )

    assert tuple(node.name for node in result) == test_case.expected_names
    assert tuple(node.kind for node in result) == test_case.expected_kinds
    assert tuple(node.upstream_names for node in result) == test_case.expected_upstream_names
    assert tuple(lifecycle_node_payload_name(node) for node in result) == (
        test_case.expected_payload_names
    )
