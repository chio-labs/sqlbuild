"""Tests for Python ingress loader lifecycle execution."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.python_nodes.models import PythonNodeGraph
from sqlbuild.compiler.python_nodes.types import PythonNodeStatus
from sqlbuild.executor.python_nodes.helpers.ingress_execution import (
    execute_ingress_python_loader_nodes,
)
from sqlbuild.executor.python_nodes.models import PythonIngressLoaderExecutorResult
from tests.unit.src.sqlbuild.executor.python_nodes.helpers._test_types import (
    PythonIngressLoaderExecutorTestCase,
)
from tests.unit.src.sqlbuild.executor.python_nodes.helpers.helpers import (
    PythonNodeContextTestAdapter,
    build_ingress_task_loader_graph,
    ingress_calls,
    ingress_loader_function,
    ingress_source_map,
    prepare_ingress_orders,
    reset_ingress_calls,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PythonIngressLoaderExecutorTestCase(
            description="runs task before dependent loader",
            selected_names=frozenset({"prepare_ingress_orders", "load_ingress_orders"}),
            expected_python_names=("prepare_ingress_orders",),
            expected_load_names=("raw_orders",),
            expected_python_statuses=(PythonNodeStatus.SUCCESS,),
            expected_load_statuses=("success",),
            expected_call_order=("prepare_ingress_orders", "load_ingress_orders"),
        )
    ],
    ids=["runs task before dependent loader"],
)
def test_given_ingress_task_to_loader_when_executing_then_runs_in_lifecycle_order(
    test_case: PythonIngressLoaderExecutorTestCase,
) -> None:
    graph: PythonNodeGraph = build_ingress_task_loader_graph()
    reset_ingress_calls()

    result: PythonIngressLoaderExecutorResult = execute_ingress_python_loader_nodes(
        python_graph=graph,
        selected_python_names=test_case.selected_names,
        loader_functions=(ingress_loader_function(),),
        source_map=ingress_source_map(),
        adapter=PythonNodeContextTestAdapter(),
        connection_config={},
        connection=object(),
        run_id="test_run",
        target="dev",
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
    assert ingress_calls() == test_case.expected_call_order
    assert result.run_state.payload(prepare_ingress_orders) == {"prepared": True}
