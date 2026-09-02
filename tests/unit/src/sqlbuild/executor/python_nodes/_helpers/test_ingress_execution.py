"""Tests for Python ingress loader lifecycle execution."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.python_nodes.models import PythonNodeGraph
from sqlbuild.compiler.python_nodes.types import PythonNodeStatus
from sqlbuild.executor.python_nodes._helpers.ingress_execution import (
    execute_ingress_python_loader_nodes,
)
from sqlbuild.executor.python_nodes.models import (
    IngressCallbacks,
    PythonIngressLoaderExecutorResult,
    PythonNodeRuntime,
)
from sqlbuild.observability import (
    EventDispatcher,
    LifecycleEvent,
    dispatcher_scope,
    invocation_scope,
)
from tests.unit.src.sqlbuild.executor.python_nodes._helpers._test_types import (
    PythonIngressLoaderExecutorTestCase,
)
from tests.unit.src.sqlbuild.executor.python_nodes._helpers.helpers import (
    PythonNodeContextTestAdapter,
    build_ingress_task_loader_graph,
    ingress_calls,
    ingress_loader_function,
    ingress_source_map,
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
    ids=lambda case: case.description,
)
def test_given_ingress_task_to_loader_when_executing_then_runs_in_lifecycle_order(
    test_case: PythonIngressLoaderExecutorTestCase,
) -> None:
    graph: PythonNodeGraph = build_ingress_task_loader_graph()
    reset_ingress_calls()
    events: list[LifecycleEvent] = []
    callback_order: list[str] = []
    dispatcher: EventDispatcher = EventDispatcher()

    def record_event(event: LifecycleEvent) -> None:
        events.append(event)
        callback_order.append(f"event:{event.event_type}:{event.payload.get('resource_name', '')}")

    dispatcher.subscribe_lifecycle(subscriber=record_event, accepts_opaque=False)

    with invocation_scope("ingress-invocation"), dispatcher_scope(dispatcher):
        result: PythonIngressLoaderExecutorResult = execute_ingress_python_loader_nodes(
            python_graph=graph,
            selected_python_names=test_case.selected_names,
            loader_functions=(ingress_loader_function(),),
            source_map=ingress_source_map(),
            runtime=PythonNodeRuntime(
                adapter=PythonNodeContextTestAdapter(),
                connection_config={},
                connection=object(),
                run_id="test_run",
                target="dev",
                vars={},
                is_reload=False,
            ),
            callbacks=IngressCallbacks(
                on_node_start=lambda name, resource_kind: callback_order.append(f"start:{name}"),
                on_node_complete=lambda completed: callback_order.append(
                    f"complete:{completed.source_name}"
                ),
            ),
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
    assert result.python_results[0].payload == {"prepared": True}
    loader_events: tuple[LifecycleEvent, ...] = tuple(
        filter(lambda event: event.payload.get("resource_name") == "raw_orders", events)
    )
    assert tuple(event.event_type for event in loader_events) == (
        "resource_attempt_started",
        "resource_attempt_completed",
    )
    assert tuple(event.run_id for event in loader_events) == ("test_run", "test_run")
    assert callback_order.index("event:resource_attempt_started:raw_orders") < (
        callback_order.index("start:raw_orders")
    )
    assert callback_order.index("start:raw_orders") < callback_order.index(
        "event:resource_attempt_completed:raw_orders"
    )
    assert callback_order.index("event:resource_attempt_completed:raw_orders") < (
        callback_order.index("complete:raw_orders")
    )
