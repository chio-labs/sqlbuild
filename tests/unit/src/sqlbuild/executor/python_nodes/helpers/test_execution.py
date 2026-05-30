"""Tests for the Python task/asset executor MVP."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.discovery.models import DiscoveredAssetFunction, DiscoveredTaskFunction
from sqlbuild.compiler.python_nodes.types import PythonNodeStatus
from sqlbuild.executor.python_nodes.helpers.execution import execute_python_nodes
from sqlbuild.executor.python_nodes.models import PythonNodeExecutorResult
from sqlbuild.shared.models import RetryPolicy
from tests.unit.src.sqlbuild.executor.python_nodes.helpers._test_types import (
    PythonNodeExecutorTestCase,
    PythonNodeRetryExecutorTestCase,
)
from tests.unit.src.sqlbuild.executor.python_nodes.helpers.helpers import (
    FlakyTask,
    PythonNodeContextTestAdapter,
    export_after_failure,
    export_after_skip,
    export_orders,
    fail_orders,
    fetch_orders,
    skip_empty_orders,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PythonNodeExecutorTestCase(
            description="executes task and asset chain with same-run state",
            expected_names=("fetch_orders", "export_orders"),
            expected_statuses=(PythonNodeStatus.SUCCESS, PythonNodeStatus.SUCCESS),
            expected_payloads=(
                {"file": "orders.json"},
                {"uri": "s3://exports/orders.json"},
            ),
            expected_materialized=(None, True),
            expected_error_fragments=(None, None),
        )
    ],
    ids=["executes task and asset chain with same-run state"],
)
def test_given_task_asset_chain_when_executing_python_nodes_then_records_results(
    test_case: PythonNodeExecutorTestCase,
) -> None:
    nodes: tuple[DiscoveredTaskFunction | DiscoveredAssetFunction, ...] = (
        DiscoveredTaskFunction(
            file_path=Path("/project/tasks/orders.py"),
            relative_path=Path("tasks/orders.py"),
            name="fetch_orders",
            function=fetch_orders,
        ),
        DiscoveredAssetFunction(
            file_path=Path("/project/assets/orders.py"),
            relative_path=Path("assets/orders.py"),
            name="export_orders",
            function=export_orders,
            depends_on=(fetch_orders,),
        ),
    )

    result: PythonNodeExecutorResult = execute_python_nodes(
        nodes=nodes,
        adapter=PythonNodeContextTestAdapter(),
        connection_config={},
        connection=object(),
        run_id="test_run",
        environment="dev",
        vars={},
        is_reload=False,
        statement_recorder=StatementRecorder(),
    )

    assert (
        tuple(node_result.node_name for node_result in result.results) == test_case.expected_names
    )
    assert (
        tuple(node_result.status for node_result in result.results) == test_case.expected_statuses
    )
    assert (
        tuple(node_result.payload for node_result in result.results) == test_case.expected_payloads
    )
    assert tuple(node_result.materialized for node_result in result.results) == (
        test_case.expected_materialized
    )
    assert tuple(node_result.error_message for node_result in result.results) == (
        test_case.expected_error_fragments
    )
    assert result.run_state.payload(fetch_orders) == test_case.expected_payloads[0]
    assert result.run_state.payload(export_orders) == test_case.expected_payloads[1]


@pytest.mark.parametrize(
    "test_case",
    [
        PythonNodeExecutorTestCase(
            description="skips downstream after hard skip",
            expected_names=("skip_empty_orders", "export_after_skip"),
            expected_statuses=(PythonNodeStatus.SKIPPED, PythonNodeStatus.SKIPPED),
            expected_payloads=(None, None),
            expected_materialized=(None, None),
            expected_error_fragments=(None, None),
        )
    ],
    ids=["skips downstream after hard skip"],
)
def test_given_hard_skipped_upstream_when_executing_python_nodes_then_skips_downstream(
    test_case: PythonNodeExecutorTestCase,
) -> None:
    nodes: tuple[DiscoveredTaskFunction | DiscoveredAssetFunction, ...] = (
        DiscoveredTaskFunction(
            file_path=Path("/project/tasks/orders.py"),
            relative_path=Path("tasks/orders.py"),
            name="skip_empty_orders",
            function=skip_empty_orders,
        ),
        DiscoveredAssetFunction(
            file_path=Path("/project/assets/orders.py"),
            relative_path=Path("assets/orders.py"),
            name="export_after_skip",
            function=export_after_skip,
            depends_on=(skip_empty_orders,),
        ),
    )

    result: PythonNodeExecutorResult = execute_python_nodes(
        nodes=nodes,
        adapter=PythonNodeContextTestAdapter(),
        connection_config={},
        connection=object(),
        run_id="test_run",
        environment="dev",
        vars={},
        is_reload=False,
        statement_recorder=StatementRecorder(),
    )

    assert (
        tuple(node_result.node_name for node_result in result.results) == test_case.expected_names
    )
    assert (
        tuple(node_result.status for node_result in result.results) == test_case.expected_statuses
    )
    assert (
        tuple(node_result.payload for node_result in result.results) == test_case.expected_payloads
    )
    assert tuple(node_result.materialized for node_result in result.results) == (
        test_case.expected_materialized
    )


@pytest.mark.parametrize(
    "test_case",
    [
        PythonNodeExecutorTestCase(
            description="blocks downstream after upstream failure",
            expected_names=("fail_orders", "export_after_failure"),
            expected_statuses=(PythonNodeStatus.FAILED, PythonNodeStatus.FAILED),
            expected_payloads=(None, None),
            expected_materialized=(None, None),
            expected_error_fragments=("API unavailable", "Upstream Python node failed"),
        )
    ],
    ids=["blocks downstream after upstream failure"],
)
def test_given_failed_upstream_when_executing_python_nodes_then_blocks_downstream(
    test_case: PythonNodeExecutorTestCase,
) -> None:
    nodes: tuple[DiscoveredTaskFunction | DiscoveredAssetFunction, ...] = (
        DiscoveredTaskFunction(
            file_path=Path("/project/tasks/orders.py"),
            relative_path=Path("tasks/orders.py"),
            name="fail_orders",
            function=fail_orders,
        ),
        DiscoveredAssetFunction(
            file_path=Path("/project/assets/orders.py"),
            relative_path=Path("assets/orders.py"),
            name="export_after_failure",
            function=export_after_failure,
            depends_on=(fail_orders,),
        ),
    )

    result: PythonNodeExecutorResult = execute_python_nodes(
        nodes=nodes,
        adapter=PythonNodeContextTestAdapter(),
        connection_config={},
        connection=object(),
        run_id="test_run",
        environment="dev",
        vars={},
        is_reload=False,
        statement_recorder=StatementRecorder(),
    )

    assert (
        tuple(node_result.node_name for node_result in result.results) == test_case.expected_names
    )
    assert (
        tuple(node_result.status for node_result in result.results) == test_case.expected_statuses
    )
    assert (
        tuple(node_result.payload for node_result in result.results) == test_case.expected_payloads
    )
    assert tuple(node_result.materialized for node_result in result.results) == (
        test_case.expected_materialized
    )
    assert result.results[0].error_message == test_case.expected_error_fragments[0]
    assert result.results[1].error_message is not None
    expected_error_fragment: str | None = test_case.expected_error_fragments[1]
    assert expected_error_fragment is not None
    assert expected_error_fragment in result.results[1].error_message


@pytest.mark.parametrize(
    "test_case",
    [
        PythonNodeRetryExecutorTestCase(
            description="retries selected exception and succeeds",
            expected_status=PythonNodeStatus.SUCCESS,
            expected_payload={"attempts": 3},
            expected_error_fragment=None,
            expected_attempts=3,
            expected_sleeps=(0.5, 1.0),
        )
    ],
    ids=["retries selected exception and succeeds"],
)
def test_given_retry_policy_when_transient_failures_then_retries_and_succeeds(
    test_case: PythonNodeRetryExecutorTestCase,
) -> None:
    flaky_task: FlakyTask = FlakyTask(failures_before_success=2, exception_type=TimeoutError)
    sleeps: list[float] = []
    nodes: tuple[DiscoveredTaskFunction | DiscoveredAssetFunction, ...] = (
        DiscoveredTaskFunction(
            file_path=Path("/project/tasks/orders.py"),
            relative_path=Path("tasks/orders.py"),
            name="flaky_task",
            function=flaky_task,
            retry=RetryPolicy(
                max_attempts=3,
                retry_on=[TimeoutError],
                initial_delay_seconds=0.5,
                backoff_multiplier=2.0,
                jitter=False,
            ),
        ),
    )

    result: PythonNodeExecutorResult = execute_python_nodes(
        nodes=nodes,
        adapter=PythonNodeContextTestAdapter(),
        connection_config={},
        connection=object(),
        run_id="test_run",
        environment="dev",
        vars={},
        is_reload=False,
        statement_recorder=StatementRecorder(),
        sleep=sleeps.append,
    )

    assert result.results[0].status == test_case.expected_status
    assert result.results[0].payload == test_case.expected_payload
    assert result.results[0].error_message == test_case.expected_error_fragment
    assert flaky_task.attempts == test_case.expected_attempts
    assert tuple(sleeps) == test_case.expected_sleeps


@pytest.mark.parametrize(
    "test_case",
    [
        PythonNodeRetryExecutorTestCase(
            description="exhausts retries and records final exception",
            expected_status=PythonNodeStatus.FAILED,
            expected_payload=None,
            expected_error_fragment="transient failure",
            expected_attempts=2,
            expected_sleeps=(0.25,),
        )
    ],
    ids=["exhausts retries and records final exception"],
)
def test_given_retry_policy_when_attempts_exhausted_then_records_final_exception(
    test_case: PythonNodeRetryExecutorTestCase,
) -> None:
    flaky_task: FlakyTask = FlakyTask(failures_before_success=3, exception_type=TimeoutError)
    sleeps: list[float] = []
    nodes: tuple[DiscoveredTaskFunction | DiscoveredAssetFunction, ...] = (
        DiscoveredTaskFunction(
            file_path=Path("/project/tasks/orders.py"),
            relative_path=Path("tasks/orders.py"),
            name="flaky_task",
            function=flaky_task,
            retry=RetryPolicy(
                max_attempts=2,
                retry_on=(TimeoutError,),
                initial_delay_seconds=0.25,
                jitter=False,
            ),
        ),
    )

    result: PythonNodeExecutorResult = execute_python_nodes(
        nodes=nodes,
        adapter=PythonNodeContextTestAdapter(),
        connection_config={},
        connection=object(),
        run_id="test_run",
        environment="dev",
        vars={},
        is_reload=False,
        statement_recorder=StatementRecorder(),
        sleep=sleeps.append,
    )

    assert result.results[0].status == test_case.expected_status
    assert result.results[0].payload == test_case.expected_payload
    assert result.results[0].error_message is not None
    expected_error_fragment: str | None = test_case.expected_error_fragment
    assert expected_error_fragment is not None
    assert expected_error_fragment in result.results[0].error_message
    assert flaky_task.attempts == test_case.expected_attempts
    assert tuple(sleeps) == test_case.expected_sleeps


@pytest.mark.parametrize(
    "test_case",
    [
        PythonNodeRetryExecutorTestCase(
            description="does not retry unlisted exception",
            expected_status=PythonNodeStatus.FAILED,
            expected_payload=None,
            expected_error_fragment="transient failure",
            expected_attempts=1,
            expected_sleeps=(),
        )
    ],
    ids=["does not retry unlisted exception"],
)
def test_given_retry_policy_when_exception_is_not_selected_then_does_not_retry(
    test_case: PythonNodeRetryExecutorTestCase,
) -> None:
    flaky_task: FlakyTask = FlakyTask(failures_before_success=1, exception_type=ValueError)
    sleeps: list[float] = []
    nodes: tuple[DiscoveredTaskFunction | DiscoveredAssetFunction, ...] = (
        DiscoveredTaskFunction(
            file_path=Path("/project/tasks/orders.py"),
            relative_path=Path("tasks/orders.py"),
            name="flaky_task",
            function=flaky_task,
            retry=RetryPolicy(max_attempts=3, retry_on=TimeoutError, jitter=False),
        ),
    )

    result: PythonNodeExecutorResult = execute_python_nodes(
        nodes=nodes,
        adapter=PythonNodeContextTestAdapter(),
        connection_config={},
        connection=object(),
        run_id="test_run",
        environment="dev",
        vars={},
        is_reload=False,
        statement_recorder=StatementRecorder(),
        sleep=sleeps.append,
    )

    assert result.results[0].status == test_case.expected_status
    assert result.results[0].payload == test_case.expected_payload
    assert result.results[0].error_message is not None
    expected_error_fragment: str | None = test_case.expected_error_fragment
    assert expected_error_fragment is not None
    assert expected_error_fragment in result.results[0].error_message
    assert flaky_task.attempts == test_case.expected_attempts
    assert tuple(sleeps) == test_case.expected_sleeps


@pytest.mark.parametrize(
    "test_case",
    [
        PythonNodeRetryExecutorTestCase(
            description="caps exponential backoff delays",
            expected_status=PythonNodeStatus.SUCCESS,
            expected_payload={"attempts": 4},
            expected_error_fragment=None,
            expected_attempts=4,
            expected_sleeps=(1.0, 1.5, 1.5),
        )
    ],
    ids=["caps exponential backoff delays"],
)
def test_given_retry_policy_when_backoff_exceeds_cap_then_sleep_is_capped(
    test_case: PythonNodeRetryExecutorTestCase,
) -> None:
    flaky_task: FlakyTask = FlakyTask(failures_before_success=3, exception_type=TimeoutError)
    sleeps: list[float] = []
    nodes: tuple[DiscoveredTaskFunction | DiscoveredAssetFunction, ...] = (
        DiscoveredTaskFunction(
            file_path=Path("/project/tasks/orders.py"),
            relative_path=Path("tasks/orders.py"),
            name="flaky_task",
            function=flaky_task,
            retry=RetryPolicy(
                max_attempts=4,
                retry_on=TimeoutError,
                initial_delay_seconds=1.0,
                backoff_multiplier=2.0,
                max_delay_seconds=1.5,
                jitter=False,
            ),
        ),
    )

    result: PythonNodeExecutorResult = execute_python_nodes(
        nodes=nodes,
        adapter=PythonNodeContextTestAdapter(),
        connection_config={},
        connection=object(),
        run_id="test_run",
        environment="dev",
        vars={},
        is_reload=False,
        statement_recorder=StatementRecorder(),
        sleep=sleeps.append,
    )

    assert result.results[0].status == test_case.expected_status
    assert result.results[0].payload == test_case.expected_payload
    assert result.results[0].error_message == test_case.expected_error_fragment
    assert flaky_task.attempts == test_case.expected_attempts
    assert tuple(sleeps) == test_case.expected_sleeps
