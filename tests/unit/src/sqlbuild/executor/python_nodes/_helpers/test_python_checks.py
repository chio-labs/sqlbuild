"""Tests for Python check execution helpers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from sqlbuild.compiler.discovery.models import DiscoveredCheckFunction
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph
from sqlbuild.compiler.python_nodes.types import PythonNodeKind, PythonNodeStatus, SkipMode
from sqlbuild.executor.node_results.models import NodeResultEnvelope
from sqlbuild.executor.python_nodes._helpers.python_checks import execute_python_check_nodes
from sqlbuild.executor.python_nodes.models import (
    PythonCheckExecutionResult,
    PythonNodeExecutionResult,
    PythonNodeRunState,
    PythonNodeRuntime,
)
from sqlbuild.provider.classes.container import ProviderContainer
from sqlbuild.provider.classes.session import ProviderSession
from sqlbuild.python_nodes.types import PythonCheckSeverity
from tests.unit.src.sqlbuild.executor.python_nodes._helpers._test_types import (
    PythonCheckExecutorTestCase,
)
from tests.unit.src.sqlbuild.executor.python_nodes._helpers.helpers import (
    ExecutionSlackProvider,
    PythonNodeContextTestAdapter,
    PythonNodeContextTestResultStore,
    build_python_check_graph,
    check_upstream_task,
    context_provider_check,
    provider_check,
    python_check_function_for_case,
)


@pytest.mark.parametrize(
    "test_case",
    (
        PythonCheckExecutorTestCase(
            description="executes passing check with upstream metadata",
            expected_passed=True,
            expected_severity=PythonCheckSeverity.ERROR,
            expected_message="passed",
            upstream_skip_mode=None,
        ),
        PythonCheckExecutorTestCase(
            description="preserves explicit warning result",
            expected_passed=False,
            expected_severity=PythonCheckSeverity.WARN,
            expected_message="warned",
            upstream_skip_mode=None,
        ),
        PythonCheckExecutorTestCase(
            description="normalizes false result as error failure",
            expected_passed=False,
            expected_severity=PythonCheckSeverity.ERROR,
            expected_message=None,
            upstream_skip_mode=None,
        ),
        PythonCheckExecutorTestCase(
            description="normalizes check exception as error failure",
            expected_passed=False,
            expected_severity=PythonCheckSeverity.ERROR,
            expected_message=None,
            upstream_skip_mode=None,
            expected_error_fragment="check exploded",
        ),
        PythonCheckExecutorTestCase(
            description="fails when upstream failed",
            expected_passed=False,
            expected_severity=PythonCheckSeverity.ERROR,
            expected_message=None,
            upstream_skip_mode=None,
            expected_error_fragment="Upstream Python node failed: upstream_task",
            upstream_status=PythonNodeStatus.FAILED,
        ),
        PythonCheckExecutorTestCase(
            description="warns when upstream skipped",
            expected_passed=False,
            expected_severity=PythonCheckSeverity.WARN,
            expected_message="Upstream Python node skipped: upstream_task",
            upstream_status=PythonNodeStatus.SKIPPED,
            upstream_skip_mode=SkipMode.HARD,
            upstream_skip_reason="not needed",
        ),
    ),
    ids=lambda case: case.description,
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
        skip_mode=test_case.upstream_skip_mode,
        skip_reason=test_case.upstream_skip_reason,
    )
    run_state.record_result(node_function=check_upstream_task, result=upstream_result)
    result_store: PythonNodeContextTestResultStore = PythonNodeContextTestResultStore(
        {
            (PythonNodeKind.TASK.value, "upstream_task"): (
                NodeResultEnvelope(
                    node_type=PythonNodeKind.TASK.value,
                    node_name="upstream_task",
                    run_id="run_1",
                    status=test_case.upstream_status.value,
                    payload={"rows": 3},
                    metadata={"rows": 3},
                    error_message=None,
                    materialized=None,
                    ts=datetime(2026, 1, 1),
                ),
            )
        }
    )

    results: tuple[PythonCheckExecutionResult, ...] = execute_python_check_nodes(
        check_functions=(check_function,),
        python_graph=graph,
        upstream_python_results=(upstream_result,),
        upstream_load_results=(),
        run_state=run_state,
        runtime=PythonNodeRuntime(
            adapter=PythonNodeContextTestAdapter(),
            connection_config={},
            connection=object(),
            run_id="run_1",
            target="dev",
            vars={},
            is_reload=False,
            result_store=result_store,
        ),
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
            upstream_skip_mode=None,
        )
    ],
    ids=lambda case: case.description,
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
        run_state=PythonNodeRunState(),
        runtime=PythonNodeRuntime(
            adapter=PythonNodeContextTestAdapter(),
            connection_config={},
            connection=object(),
            run_id="run_1",
            target="dev",
            vars={},
            is_reload=False,
            providers=providers,
        ),
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
            description="exposes providers on check context",
            expected_passed=True,
            expected_severity=PythonCheckSeverity.ERROR,
            expected_message=None,
            upstream_skip_mode=None,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_provider_container_when_executing_python_check_then_context_exposes_providers(
    test_case: PythonCheckExecutorTestCase,
) -> None:
    check_function: DiscoveredCheckFunction = DiscoveredCheckFunction(
        file_path=Path(__file__),
        relative_path=Path(Path(__file__).name),
        name="context_provider_check",
        function=context_provider_check,
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
        run_state=PythonNodeRunState(),
        runtime=PythonNodeRuntime(
            adapter=PythonNodeContextTestAdapter(),
            connection_config={},
            connection=object(),
            run_id="run_1",
            target="dev",
            vars={},
            is_reload=False,
            providers=providers,
        ),
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
            upstream_skip_mode=None,
            expected_error_fragment=(
                "Provider parameter 'slack_provider' requires provider 'slack_provider', "
                "but no provider container is available"
            ),
        )
    ],
    ids=lambda case: case.description,
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
        run_state=PythonNodeRunState(),
        runtime=PythonNodeRuntime(
            adapter=PythonNodeContextTestAdapter(),
            connection_config={},
            connection=object(),
            run_id="run_1",
            target="dev",
            vars={},
            is_reload=False,
        ),
    )

    assert len(results) == 1
    result: PythonCheckExecutionResult = results[0]
    assert result.passed == test_case.expected_passed
    assert result.severity == test_case.expected_severity
    assert result.message == test_case.expected_message
    assert test_case.expected_error_fragment is not None
    assert test_case.expected_error_fragment in (result.error_message or "")
