"""Tests for the generic lifecycle scheduler."""

from __future__ import annotations

import pytest

from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.executor.shared.helpers.lifecycle_scheduler import run_lifecycle_scheduler
from sqlbuild.executor.shared.models.lifecycle_scheduler import (
    LifecycleExecutionNode,
    LifecycleSchedulerResult,
)
from sqlbuild.executor.shared.types import LifecycleNodeStatus
from tests.unit.src.sqlbuild.executor.shared.helpers._test_types import (
    LifecycleSchedulerErrorTestCase,
    LifecycleSchedulerTestCase,
)
from tests.unit.src.sqlbuild.executor.shared.helpers.helpers import (
    lifecycle_success,
    record_lifecycle_maybe_failure,
    record_lifecycle_success,
)


@pytest.mark.parametrize(
    "test_case",
    [
        LifecycleSchedulerTestCase(
            description="runs mixed nodes in topological order",
            expected_order=("load_pages", "summarize_pages", "load_orders"),
            expected_statuses=(
                LifecycleNodeStatus.SUCCESS,
                LifecycleNodeStatus.SUCCESS,
                LifecycleNodeStatus.SUCCESS,
            ),
            expected_skip_reasons=(None, None, None),
        )
    ],
    ids=["runs mixed nodes in topological order"],
)
def test_given_mixed_lifecycle_nodes_when_running_scheduler_then_runs_in_topological_order(
    test_case: LifecycleSchedulerTestCase,
) -> None:
    calls: list[str] = []
    nodes: tuple[LifecycleExecutionNode, ...] = (
        LifecycleExecutionNode(
            name="load_orders", kind="loader", upstream_names=("summarize_pages",)
        ),
        LifecycleExecutionNode(name="load_pages", kind="loader"),
        LifecycleExecutionNode(name="summarize_pages", kind="task", upstream_names=("load_pages",)),
    )

    result: LifecycleSchedulerResult = run_lifecycle_scheduler(
        nodes=nodes,
        handler=lambda node: record_lifecycle_success(node=node, calls=calls),
    )

    assert calls == list(test_case.expected_order)
    assert tuple(node_result.name for node_result in result.results) == test_case.expected_order
    assert (
        tuple(node_result.status for node_result in result.results) == test_case.expected_statuses
    )
    assert tuple(node_result.skip_reason for node_result in result.results) == (
        test_case.expected_skip_reasons
    )


@pytest.mark.parametrize(
    "test_case",
    [
        LifecycleSchedulerTestCase(
            description="skips downstream after failed upstream",
            expected_order=("load_pages", "summarize_pages", "load_orders"),
            expected_statuses=(
                LifecycleNodeStatus.SUCCESS,
                LifecycleNodeStatus.FAILED,
                LifecycleNodeStatus.SKIPPED,
            ),
            expected_skip_reasons=(None, None, "Upstream node did not succeed: summarize_pages"),
        )
    ],
    ids=["skips downstream after failed upstream"],
)
def test_given_failed_lifecycle_node_when_running_scheduler_then_skips_downstream(
    test_case: LifecycleSchedulerTestCase,
) -> None:
    calls: list[str] = []
    nodes: tuple[LifecycleExecutionNode, ...] = (
        LifecycleExecutionNode(name="load_pages", kind="loader"),
        LifecycleExecutionNode(name="summarize_pages", kind="task", upstream_names=("load_pages",)),
        LifecycleExecutionNode(
            name="load_orders", kind="loader", upstream_names=("summarize_pages",)
        ),
    )

    result: LifecycleSchedulerResult = run_lifecycle_scheduler(
        nodes=nodes,
        handler=lambda node: record_lifecycle_maybe_failure(node=node, calls=calls),
    )

    assert calls == ["load_pages", "summarize_pages"]
    assert tuple(node_result.name for node_result in result.results) == test_case.expected_order
    assert (
        tuple(node_result.status for node_result in result.results) == test_case.expected_statuses
    )
    assert tuple(node_result.skip_reason for node_result in result.results) == (
        test_case.expected_skip_reasons
    )


@pytest.mark.parametrize(
    "test_case",
    [
        LifecycleSchedulerErrorTestCase(
            description="raises for unknown dependency",
            expected_error_fragment="depends on unknown node 'missing'",
        )
    ],
    ids=["raises for unknown dependency"],
)
def test_given_unknown_dependency_when_running_scheduler_then_raises_input_error(
    test_case: LifecycleSchedulerErrorTestCase,
) -> None:
    nodes: tuple[LifecycleExecutionNode, ...] = (
        LifecycleExecutionNode(name="summarize_pages", kind="task", upstream_names=("missing",)),
    )

    with pytest.raises(ExecutorInputError) as exc_info:
        run_lifecycle_scheduler(nodes=nodes, handler=lifecycle_success)

    assert test_case.expected_error_fragment in str(exc_info.value)
