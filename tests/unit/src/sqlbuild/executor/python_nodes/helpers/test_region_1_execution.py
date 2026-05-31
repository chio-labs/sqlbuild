"""Tests for Region 1 Python/loader lifecycle execution."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.python_nodes.models import PythonNodeGraph
from sqlbuild.compiler.python_nodes.types import PythonNodeStatus
from sqlbuild.executor.python_nodes.helpers.region_1_execution import (
    execute_region_1_python_loader_nodes,
)
from sqlbuild.executor.python_nodes.models import Region1PythonLoaderExecutorResult
from tests.unit.src.sqlbuild.executor.python_nodes.helpers._test_types import (
    Region1PythonLoaderExecutorTestCase,
)
from tests.unit.src.sqlbuild.executor.python_nodes.helpers.helpers import (
    PythonNodeContextTestAdapter,
    build_region_1_task_loader_graph,
    prepare_region_1_orders,
    region_1_calls,
    region_1_loader_function,
    region_1_source_map,
    reset_region_1_calls,
)


@pytest.mark.parametrize(
    "test_case",
    [
        Region1PythonLoaderExecutorTestCase(
            description="runs task before dependent loader",
            selected_names=frozenset({"prepare_region_1_orders", "load_region_1_orders"}),
            expected_python_names=("prepare_region_1_orders",),
            expected_load_names=("raw_orders",),
            expected_python_statuses=(PythonNodeStatus.SUCCESS,),
            expected_load_statuses=("success",),
            expected_call_order=("prepare_region_1_orders", "load_region_1_orders"),
        )
    ],
    ids=["runs task before dependent loader"],
)
def test_given_region_1_task_to_loader_when_executing_then_runs_in_lifecycle_order(
    test_case: Region1PythonLoaderExecutorTestCase,
) -> None:
    graph: PythonNodeGraph = build_region_1_task_loader_graph()
    reset_region_1_calls()

    result: Region1PythonLoaderExecutorResult = execute_region_1_python_loader_nodes(
        python_graph=graph,
        selected_python_names=test_case.selected_names,
        loader_functions=(region_1_loader_function(),),
        source_map=region_1_source_map(),
        adapter=PythonNodeContextTestAdapter(),
        connection_config={},
        connection=object(),
        run_id="test_run",
        environment="dev",
        vars={},
        is_reload=False,
    )

    assert tuple(node_result.node_name for node_result in result.python_results) == (
        test_case.expected_python_names
    )
    assert tuple(load_result.source_name for load_result in result.load_results) == (
        test_case.expected_load_names
    )
    assert tuple(node_result.status for node_result in result.python_results) == (
        test_case.expected_python_statuses
    )
    assert tuple(load_result.status.value for load_result in result.load_results) == (
        test_case.expected_load_statuses
    )
    assert region_1_calls() == test_case.expected_call_order
    assert result.run_state.payload(prepare_region_1_orders) == {"prepared": True}
