"""Tests for generic Python-node scheduler helpers."""

from __future__ import annotations

import pytest

from sqlbuild.executor.shared.helpers.python_node_scheduler import (
    build_python_node_in_degree,
    build_python_node_ready_queue,
)
from tests.unit.src.sqlbuild.executor.python_nodes.helpers._test_types import (
    PythonNodeSchedulerTestCase,
)
from tests.unit.src.sqlbuild.executor.python_nodes.helpers.helpers import apply_completion_order


@pytest.mark.parametrize(
    "test_case",
    [
        PythonNodeSchedulerTestCase(
            description="unlocks linear downstream nodes after upstream completion",
            node_names=("fetch", "load"),
            upstream_names={"fetch": (), "load": ("fetch",)},
            downstream_names={"fetch": ("load",), "load": ()},
            completion_order=("fetch",),
            expected_initial_ready=("fetch",),
            expected_final_ready=("fetch", "load"),
            expected_final_in_degree={"fetch": 0, "load": 0},
        ),
        PythonNodeSchedulerTestCase(
            description="unlocks fan-out downstream nodes in downstream order",
            node_names=("fetch", "load_orders", "load_customers"),
            upstream_names={
                "fetch": (),
                "load_orders": ("fetch",),
                "load_customers": ("fetch",),
            },
            downstream_names={"fetch": ("load_orders", "load_customers")},
            completion_order=("fetch",),
            expected_initial_ready=("fetch",),
            expected_final_ready=("fetch", "load_orders", "load_customers"),
            expected_final_in_degree={"fetch": 0, "load_orders": 0, "load_customers": 0},
        ),
        PythonNodeSchedulerTestCase(
            description="unlocks fan-in downstream only after all upstreams complete",
            node_names=("fetch_orders", "fetch_customers", "load_enriched"),
            upstream_names={
                "fetch_orders": (),
                "fetch_customers": (),
                "load_enriched": ("fetch_orders", "fetch_customers"),
            },
            downstream_names={
                "fetch_orders": ("load_enriched",),
                "fetch_customers": ("load_enriched",),
            },
            completion_order=("fetch_orders", "fetch_customers"),
            expected_initial_ready=("fetch_orders", "fetch_customers"),
            expected_final_ready=("fetch_orders", "fetch_customers", "load_enriched"),
            expected_final_in_degree={
                "fetch_orders": 0,
                "fetch_customers": 0,
                "load_enriched": 0,
            },
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_python_node_dag_when_completing_nodes_then_unlocks_ready_nodes(
    test_case: PythonNodeSchedulerTestCase,
) -> None:
    in_degree: dict[str, int] = build_python_node_in_degree(
        node_names=test_case.node_names,
        upstream_names=test_case.upstream_names,
    )
    ready: list[str] = build_python_node_ready_queue(
        node_names=test_case.node_names,
        in_degree=in_degree,
    )

    assert tuple(ready) == test_case.expected_initial_ready

    in_degree, ready = apply_completion_order(
        completion_order=test_case.completion_order,
        in_degree=in_degree,
        ready=ready,
        downstream_names=test_case.downstream_names,
    )

    assert tuple(ready) == test_case.expected_final_ready
    assert in_degree == test_case.expected_final_in_degree
