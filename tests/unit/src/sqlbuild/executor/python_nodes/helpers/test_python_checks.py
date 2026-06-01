"""Tests for Python check execution helpers."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.discovery.models import DiscoveredCheckFunction
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph
from sqlbuild.compiler.python_nodes.types import PythonNodeKind, PythonNodeStatus, SkipMode
from sqlbuild.executor.python_nodes.helpers.python_checks import execute_python_check_nodes
from sqlbuild.executor.python_nodes.models import (
    PythonCheckExecutionResult,
    PythonNodeExecutionResult,
    PythonNodeRunState,
)
from sqlbuild.shared.types import PythonCheckSeverity
from tests.unit.src.sqlbuild.executor.python_nodes.helpers._test_types import (
    PythonCheckExecutorTestCase,
)
from tests.unit.src.sqlbuild.executor.python_nodes.helpers.helpers import (
    PythonNodeContextTestAdapter,
    build_python_check_graph,
    check_upstream_task,
    python_check_function_for_case,
)

CHECK_EXECUTOR_TEST_CASES: tuple[PythonCheckExecutorTestCase, ...] = (
    PythonCheckExecutorTestCase(
        description="executes passing check with upstream metadata",
        expected_passed=True,
        expected_severity=PythonCheckSeverity.ERROR,
        expected_message="passed",
    ),
    PythonCheckExecutorTestCase(
        description="preserves explicit warning result",
        expected_passed=False,
        expected_severity=PythonCheckSeverity.WARN,
        expected_message="warned",
    ),
    PythonCheckExecutorTestCase(
        description="normalizes false result as error failure",
        expected_passed=False,
        expected_severity=PythonCheckSeverity.ERROR,
        expected_message=None,
    ),
    PythonCheckExecutorTestCase(
        description="normalizes check exception as error failure",
        expected_passed=False,
        expected_severity=PythonCheckSeverity.ERROR,
        expected_message=None,
        expected_error_fragment="check exploded",
    ),
    PythonCheckExecutorTestCase(
        description="fails when upstream failed",
        expected_passed=False,
        expected_severity=PythonCheckSeverity.ERROR,
        expected_message=None,
        expected_error_fragment="Upstream Python node failed: upstream_task",
        upstream_status=PythonNodeStatus.FAILED,
    ),
    PythonCheckExecutorTestCase(
        description="warns when upstream skipped",
        expected_passed=False,
        expected_severity=PythonCheckSeverity.WARN,
        expected_message="Upstream Python node skipped: upstream_task",
        upstream_status=PythonNodeStatus.SKIPPED,
        upstream_skip_reason="not needed",
    ),
)


@pytest.mark.parametrize(
    "test_case",
    CHECK_EXECUTOR_TEST_CASES,
    ids=[case.description for case in CHECK_EXECUTOR_TEST_CASES],
)
def test_given_python_check_when_executing_then_returns_expected_result(
    test_case: PythonCheckExecutorTestCase,
) -> None:
    check_function: DiscoveredCheckFunction = python_check_function_for_case(test_case.description)
    graph: PythonNodeGraph = build_python_check_graph(check_function=check_function)
    run_state: PythonNodeRunState = PythonNodeRunState()
    upstream_result: PythonNodeExecutionResult = PythonNodeExecutionResult(
        node_name="upstream_task",
        kind=PythonNodeKind.TASK,
        status=test_case.upstream_status,
        payload={"rows": 3},
        metadata={"rows": 3},
        skip_mode=SkipMode.DOWNSTREAM
        if test_case.upstream_status == PythonNodeStatus.SKIPPED
        else None,
        skip_reason=test_case.upstream_skip_reason,
    )
    run_state.record_result(node_function=check_upstream_task, result=upstream_result)

    results: tuple[PythonCheckExecutionResult, ...] = execute_python_check_nodes(
        check_functions=(check_function,),
        python_graph=graph,
        upstream_python_results=(upstream_result,),
        upstream_load_results=(),
        adapter=PythonNodeContextTestAdapter(),
        connection_config={},
        connection=object(),
        run_id="run_1",
        environment="dev",
        vars={},
        is_reload=False,
        run_state=run_state,
    )

    assert len(results) == 1
    result: PythonCheckExecutionResult = results[0]
    assert result.passed == test_case.expected_passed
    assert result.severity == test_case.expected_severity
    assert result.message == test_case.expected_message
    expected_error_fragment: str = test_case.expected_error_fragment or ""
    assert expected_error_fragment in (result.error_message or "")
