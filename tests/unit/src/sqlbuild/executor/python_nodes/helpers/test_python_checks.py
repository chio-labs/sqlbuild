"""Tests for Python check execution helpers."""

from __future__ import annotations

from pathlib import Path

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
from sqlbuild.provider.classes.container import ProviderContainer
from sqlbuild.provider.classes.session import ProviderSession
from sqlbuild.shared.types import PythonCheckSeverity
from tests.unit.src.sqlbuild.executor.python_nodes.helpers._test_types import (
    PythonCheckExecutorTestCase,
)
from tests.unit.src.sqlbuild.executor.python_nodes.helpers.helpers import (
    ExecutionSlackProvider,
    PythonNodeContextTestAdapter,
    build_python_check_graph,
    check_upstream_task,
    provider_check,
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
        skip_mode=SkipMode.HARD if test_case.upstream_status == PythonNodeStatus.SKIPPED else None,
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
        target="dev",
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


@pytest.mark.parametrize(
    "test_case",
    [
        PythonCheckExecutorTestCase(
            description="injects provider into check execution",
            expected_passed=True,
            expected_severity=PythonCheckSeverity.ERROR,
            expected_message=None,
        )
    ],
    ids=["injects provider into check execution"],
)
def test_given_provider_parameter_when_executing_python_check_then_provider_is_injected(
    test_case: PythonCheckExecutorTestCase,
) -> None:
    check_function: DiscoveredCheckFunction = DiscoveredCheckFunction(
        file_path=Path(__file__),
        relative_path=Path(Path(__file__).name),
        name="provider_check",
        function=provider_check,
        depends_on=(),
    )
    graph: PythonNodeGraph = build_python_check_graph(check_function=check_function)
    providers: ProviderContainer = ProviderSession(
        {"slack_provider": ExecutionSlackProvider(label="slack")}
    ).providers

    results: tuple[PythonCheckExecutionResult, ...] = execute_python_check_nodes(
        check_functions=(check_function,),
        python_graph=graph,
        upstream_python_results=(),
        upstream_load_results=(),
        adapter=PythonNodeContextTestAdapter(),
        connection_config={},
        connection=object(),
        run_id="run_1",
        target="dev",
        vars={},
        is_reload=False,
        run_state=PythonNodeRunState(),
        providers=providers,
    )

    assert len(results) == 1
    result: PythonCheckExecutionResult = results[0]
    assert result.passed == test_case.expected_passed
    assert result.severity == test_case.expected_severity
    assert result.message == test_case.expected_message


@pytest.mark.parametrize(
    "test_case",
    [
        PythonCheckExecutorTestCase(
            description="normalizes missing provider container as check failure",
            expected_passed=False,
            expected_severity=PythonCheckSeverity.ERROR,
            expected_message=None,
            expected_error_fragment=(
                "Provider parameter 'slack_provider' requires provider 'slack_provider', "
                "but no provider container is available"
            ),
        )
    ],
    ids=["normalizes missing provider container as check failure"],
)
def test_given_missing_provider_container_when_executing_python_check_then_failure_is_recorded(
    test_case: PythonCheckExecutorTestCase,
) -> None:
    check_function: DiscoveredCheckFunction = DiscoveredCheckFunction(
        file_path=Path(__file__),
        relative_path=Path(Path(__file__).name),
        name="provider_check",
        function=provider_check,
        depends_on=(),
    )
    graph: PythonNodeGraph = build_python_check_graph(check_function=check_function)

    results: tuple[PythonCheckExecutionResult, ...] = execute_python_check_nodes(
        check_functions=(check_function,),
        python_graph=graph,
        upstream_python_results=(),
        upstream_load_results=(),
        adapter=PythonNodeContextTestAdapter(),
        connection_config={},
        connection=object(),
        run_id="run_1",
        target="dev",
        vars={},
        is_reload=False,
        run_state=PythonNodeRunState(),
    )

    assert len(results) == 1
    result: PythonCheckExecutionResult = results[0]
    assert result.passed == test_case.expected_passed
    assert result.severity == test_case.expected_severity
    assert result.message == test_case.expected_message
    assert test_case.expected_error_fragment is not None
    assert test_case.expected_error_fragment in (result.error_message or "")
