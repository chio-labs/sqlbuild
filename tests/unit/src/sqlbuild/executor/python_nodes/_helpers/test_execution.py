"""Tests for the Python task/asset executor MVP."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from sqlbuild.adapter.classes.statement_recorder import StatementRecorder
from sqlbuild.compiler.discovery.models import DiscoveredAssetFunction, DiscoveredTaskFunction
from sqlbuild.compiler.python_nodes.types import PythonNodeStatus
from sqlbuild.executor.node_results.classes.standard_store import StandardNodeResultStore
from sqlbuild.executor.node_results.main.standard_store import build_standard_node_result_store
from sqlbuild.executor.python_nodes._helpers.execution import (
    execute_python_nodes,
    execute_ready_python_node,
)
from sqlbuild.executor.python_nodes.models import (
    PythonNodeExecutionResult,
    PythonNodeExecutorResult,
    PythonNodeRunState,
    PythonNodeRuntime,
)
from sqlbuild.provider.classes.container import ProviderContainer
from sqlbuild.provider.classes.session import ProviderSession
from sqlbuild.python_nodes.models import RetryPolicy
from tests.unit.src.sqlbuild.executor.python_nodes._helpers._test_types import (
    PythonNodeExecutorTestCase,
    PythonNodeRetryExecutorTestCase,
)
from tests.unit.src.sqlbuild.executor.python_nodes._helpers.helpers import (
    EXPECTED_END_CURSOR_TS,
    EXPECTED_START_CURSOR_TS,
    ExecutionSlackProvider,
    FlakyTask,
    PythonNodeContextTestAdapter,
    context_provider_asset,
    context_provider_task,
    cursor_window,
    export_after_failure,
    export_after_mixed_skip,
    export_after_skip,
    export_orders,
    fail_orders,
    fetch_orders,
    hard_skip_empty_orders,
    missing_context_provider_task,
    provider_asset,
    provider_task,
    skip_empty_orders,
    successful_sibling,
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
    ids=lambda case: case.description,
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
        statement_recorder=StatementRecorder(),
        runtime=PythonNodeRuntime(
            adapter=PythonNodeContextTestAdapter(),
            connection_config={},
            connection=object(),
            run_id="test_run",
            target="dev",
            vars={},
            is_reload=False,
            default_schema="default_schema",
        ),
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


@pytest.mark.parametrize(
    "test_case",
    [
        PythonNodeExecutorTestCase(
            description="injects provider into task and asset execution",
            expected_names=("provider_task", "provider_asset"),
            expected_statuses=(PythonNodeStatus.SUCCESS, PythonNodeStatus.SUCCESS),
            expected_payloads=(
                {"target": "dev", "provider": "slack"},
                {"target": "dev", "provider": "slack"},
            ),
            expected_materialized=(None, None),
            expected_error_fragments=(None, None),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_provider_parameters_when_executing_python_nodes_then_providers_are_injected(
    test_case: PythonNodeExecutorTestCase,
) -> None:
    nodes: tuple[DiscoveredTaskFunction | DiscoveredAssetFunction, ...] = (
        DiscoveredTaskFunction(
            file_path=Path("/project/tasks/provider.py"),
            relative_path=Path("tasks/provider.py"),
            name="provider_task",
            function=provider_task,
        ),
        DiscoveredAssetFunction(
            file_path=Path("/project/assets/provider.py"),
            relative_path=Path("assets/provider.py"),
            name="provider_asset",
            function=provider_asset,
        ),
    )
    providers: ProviderContainer = ProviderSession(
        {"slack_provider": ExecutionSlackProvider(label="slack")}
    ).providers

    result: PythonNodeExecutorResult = execute_python_nodes(
        nodes=nodes,
        statement_recorder=StatementRecorder(),
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

    assert tuple(item.node_name for item in result.results) == test_case.expected_names
    assert tuple(item.status for item in result.results) == test_case.expected_statuses
    assert tuple(item.payload for item in result.results) == test_case.expected_payloads


@pytest.mark.parametrize(
    "test_case",
    [
        PythonNodeExecutorTestCase(
            description="exposes providers on task and asset contexts",
            expected_names=("context_provider_task", "context_provider_asset"),
            expected_statuses=(PythonNodeStatus.SUCCESS, PythonNodeStatus.SUCCESS),
            expected_payloads=(
                {"attr": "slack", "item": "slack"},
                {"attr": "slack", "item": "slack"},
            ),
            expected_materialized=(None, None),
            expected_error_fragments=(None, None),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_provider_container_when_executing_python_nodes_then_context_exposes_providers(
    test_case: PythonNodeExecutorTestCase,
) -> None:
    nodes: tuple[DiscoveredTaskFunction | DiscoveredAssetFunction, ...] = (
        DiscoveredTaskFunction(
            file_path=Path("/project/tasks/provider.py"),
            relative_path=Path("tasks/provider.py"),
            name="context_provider_task",
            function=context_provider_task,
        ),
        DiscoveredAssetFunction(
            file_path=Path("/project/assets/provider.py"),
            relative_path=Path("assets/provider.py"),
            name="context_provider_asset",
            function=context_provider_asset,
        ),
    )
    providers: ProviderContainer = ProviderSession(
        {"slack_provider": ExecutionSlackProvider(label="slack")}
    ).providers

    result: PythonNodeExecutorResult = execute_python_nodes(
        nodes=nodes,
        statement_recorder=StatementRecorder(),
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

    assert tuple(item.node_name for item in result.results) == test_case.expected_names
    assert tuple(item.status for item in result.results) == test_case.expected_statuses
    assert tuple(item.payload for item in result.results) == test_case.expected_payloads


@pytest.mark.parametrize(
    "test_case",
    [
        PythonNodeExecutorTestCase(
            description="normalizes missing provider container as task and asset failures",
            expected_names=("provider_task", "provider_asset"),
            expected_statuses=(PythonNodeStatus.FAILED, PythonNodeStatus.FAILED),
            expected_payloads=(None, None),
            expected_materialized=(None, None),
            expected_error_fragments=(
                "Provider parameter 'slack_provider' requires provider 'slack_provider', "
                "but no provider container is available",
                "Provider parameter 'slack_provider' requires provider 'slack_provider', "
                "but no provider container is available",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_missing_provider_container_when_executing_python_nodes_then_failures_are_recorded(
    test_case: PythonNodeExecutorTestCase,
) -> None:
    nodes: tuple[DiscoveredTaskFunction | DiscoveredAssetFunction, ...] = (
        DiscoveredTaskFunction(
            file_path=Path("/project/tasks/provider.py"),
            relative_path=Path("tasks/provider.py"),
            name="provider_task",
            function=provider_task,
        ),
        DiscoveredAssetFunction(
            file_path=Path("/project/assets/provider.py"),
            relative_path=Path("assets/provider.py"),
            name="provider_asset",
            function=provider_asset,
        ),
    )

    result: PythonNodeExecutorResult = execute_python_nodes(
        nodes=nodes,
        statement_recorder=StatementRecorder(),
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

    assert tuple(item.node_name for item in result.results) == test_case.expected_names
    assert tuple(item.status for item in result.results) == test_case.expected_statuses
    assert tuple(item.payload for item in result.results) == test_case.expected_payloads
    assert tuple(item.materialized for item in result.results) == test_case.expected_materialized
    for item, expected in zip(result.results, test_case.expected_error_fragments, strict=True):
        assert expected is not None
        assert expected in (item.error_message or "")


@pytest.mark.parametrize(
    "test_case",
    [
        PythonNodeExecutorTestCase(
            description="missing context provider lookup records task failure",
            expected_names=("missing_context_provider_task",),
            expected_statuses=(PythonNodeStatus.FAILED,),
            expected_payloads=(None,),
            expected_materialized=(None,),
            expected_error_fragments=(
                "Provider 'slack_provider' was not found. Available providers: none",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_missing_context_provider_when_executing_python_node_then_failure_is_recorded(
    test_case: PythonNodeExecutorTestCase,
) -> None:
    result: PythonNodeExecutorResult = execute_python_nodes(
        nodes=(
            DiscoveredTaskFunction(
                file_path=Path("/project/tasks/provider.py"),
                relative_path=Path("tasks/provider.py"),
                name="missing_context_provider_task",
                function=missing_context_provider_task,
            ),
        ),
        statement_recorder=StatementRecorder(),
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

    assert tuple(item.node_name for item in result.results) == test_case.expected_names
    assert tuple(item.status for item in result.results) == test_case.expected_statuses
    assert tuple(item.payload for item in result.results) == test_case.expected_payloads
    expected_error_fragment: str | None = test_case.expected_error_fragments[0]
    assert expected_error_fragment is not None
    assert expected_error_fragment in (result.results[0].error_message or "")


@pytest.mark.parametrize(
    "test_case",
    [
        PythonNodeExecutorTestCase(
            description="executes one ready asset with existing run state",
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
    ids=lambda case: case.description,
)
def test_given_ready_python_node_when_executing_then_uses_existing_run_state(
    test_case: PythonNodeExecutorTestCase,
) -> None:
    run_state: PythonNodeRunState = PythonNodeRunState()
    task_node: DiscoveredTaskFunction = DiscoveredTaskFunction(
        file_path=Path("/project/tasks/orders.py"),
        relative_path=Path("tasks/orders.py"),
        name="fetch_orders",
        function=fetch_orders,
    )
    asset_node: DiscoveredAssetFunction = DiscoveredAssetFunction(
        file_path=Path("/project/assets/orders.py"),
        relative_path=Path("assets/orders.py"),
        name="export_orders",
        function=export_orders,
        depends_on=(fetch_orders,),
    )

    adapter: PythonNodeContextTestAdapter = PythonNodeContextTestAdapter()
    result_store: StandardNodeResultStore = build_standard_node_result_store(
        adapter=adapter,
        connection=object(),
        database=None,
        schema="default_schema",
    )

    task_result: PythonNodeExecutionResult = execute_ready_python_node(
        node=task_node,
        upstream_results=(),
        statement_recorder=StatementRecorder(),
        run_state=run_state,
        runtime=PythonNodeRuntime(
            adapter=adapter,
            connection_config={},
            connection=result_store.connection,
            run_id="test_run",
            target="dev",
            vars={},
            is_reload=False,
            default_schema="default_schema",
            result_store=result_store,
        ),
    )
    run_state.record_result(node_function=task_node.function, result=task_result)
    asset_result: PythonNodeExecutionResult = execute_ready_python_node(
        node=asset_node,
        upstream_results=(task_result,),
        statement_recorder=StatementRecorder(),
        run_state=run_state,
        runtime=PythonNodeRuntime(
            adapter=adapter,
            connection_config={},
            connection=result_store.connection,
            run_id="test_run",
            target="dev",
            vars={},
            is_reload=False,
            default_schema="default_schema",
            result_store=result_store,
        ),
    )

    assert (task_result.node_name, asset_result.node_name) == test_case.expected_names
    assert (task_result.status, asset_result.status) == test_case.expected_statuses
    assert (task_result.payload, asset_result.payload) == test_case.expected_payloads
    assert (task_result.materialized, asset_result.materialized) == (
        test_case.expected_materialized
    )


@pytest.mark.parametrize(
    "test_case",
    [
        PythonNodeExecutorTestCase(
            description="passes cursor overrides into task context",
            expected_names=("cursor_window",),
            expected_statuses=(PythonNodeStatus.SUCCESS,),
            expected_payloads=(
                {
                    "start_cursor_ts": EXPECTED_START_CURSOR_TS,
                    "end_cursor_ts": EXPECTED_END_CURSOR_TS,
                    "start_cursor_int": 10,
                    "end_cursor_int": 20,
                },
            ),
            expected_materialized=(None,),
            expected_error_fragments=(None,),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_cursor_overrides_when_executing_python_nodes_then_context_receives_cursors(
    test_case: PythonNodeExecutorTestCase,
) -> None:
    nodes: tuple[DiscoveredTaskFunction | DiscoveredAssetFunction, ...] = (
        DiscoveredTaskFunction(
            file_path=Path("/project/tasks/orders.py"),
            relative_path=Path("tasks/orders.py"),
            name="cursor_window",
            function=cursor_window,
        ),
    )

    result: PythonNodeExecutorResult = execute_python_nodes(
        nodes=nodes,
        statement_recorder=StatementRecorder(),
        runtime=PythonNodeRuntime(
            adapter=PythonNodeContextTestAdapter(),
            connection_config={},
            connection=object(),
            run_id="test_run",
            target="dev",
            vars={},
            is_reload=False,
            start_cursor_ts=EXPECTED_START_CURSOR_TS,
            end_cursor_ts=EXPECTED_END_CURSOR_TS,
            start_cursor_int=10,
            end_cursor_int=20,
        ),
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
            description="skips downstream after hard skip",
            expected_names=("skip_empty_orders", "export_after_skip"),
            expected_statuses=(PythonNodeStatus.SKIPPED, PythonNodeStatus.SKIPPED),
            expected_payloads=(None, None),
            expected_materialized=(None, None),
            expected_error_fragments=(None, None),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_hard_skipped_upstream_when_executing_python_nodes_then_skips_downstream(
    test_case: PythonNodeExecutorTestCase,
) -> None:
    nodes: tuple[DiscoveredTaskFunction | DiscoveredAssetFunction, ...] = (
        DiscoveredTaskFunction(
            file_path=Path("/project/tasks/orders.py"),
            relative_path=Path("tasks/orders.py"),
            name="skip_empty_orders",
            function=hard_skip_empty_orders,
        ),
        DiscoveredAssetFunction(
            file_path=Path("/project/assets/orders.py"),
            relative_path=Path("assets/orders.py"),
            name="export_after_skip",
            function=export_after_skip,
            depends_on=(hard_skip_empty_orders,),
        ),
    )

    result: PythonNodeExecutorResult = execute_python_nodes(
        nodes=nodes,
        statement_recorder=StatementRecorder(),
        runtime=PythonNodeRuntime(
            adapter=PythonNodeContextTestAdapter(),
            connection_config={},
            connection=object(),
            run_id="test_run",
            target="dev",
            vars={},
            is_reload=False,
        ),
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
    (
        PythonNodeExecutorTestCase(
            description="runs downstream when soft-skipped branch has successful sibling",
            expected_names=(
                "skip_empty_orders",
                "successful_sibling",
                "export_after_skip",
                "export_after_mixed_skip",
            ),
            expected_statuses=(
                PythonNodeStatus.SKIPPED,
                PythonNodeStatus.SUCCESS,
                PythonNodeStatus.SKIPPED,
                PythonNodeStatus.SUCCESS,
            ),
            expected_payloads=(
                None,
                {"status": "ready"},
                None,
                {"uri": "s3://exports/orders.json"},
            ),
            expected_materialized=(None, None, None, True),
            expected_error_fragments=(None, None, None, None),
            skip_function=skip_empty_orders,
        ),
        PythonNodeExecutorTestCase(
            description="skips downstream when hard-skipped branch has successful sibling",
            expected_names=(
                "skip_empty_orders",
                "successful_sibling",
                "export_after_skip",
                "export_after_mixed_skip",
            ),
            expected_statuses=(
                PythonNodeStatus.SKIPPED,
                PythonNodeStatus.SUCCESS,
                PythonNodeStatus.SKIPPED,
                PythonNodeStatus.SKIPPED,
            ),
            expected_payloads=(None, {"status": "ready"}, None, None),
            expected_materialized=(None, None, None, None),
            expected_error_fragments=(None, None, None, None),
            skip_function=hard_skip_empty_orders,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_mixed_python_skips_when_executing_nodes_then_fan_in_matches_mode(
    test_case: PythonNodeExecutorTestCase,
) -> None:
    skip_function: Callable[..., object] | None = test_case.skip_function
    assert skip_function is not None
    nodes: tuple[DiscoveredTaskFunction | DiscoveredAssetFunction, ...] = (
        DiscoveredTaskFunction(
            file_path=Path("/project/tasks/orders.py"),
            relative_path=Path("tasks/orders.py"),
            name="skip_empty_orders",
            function=skip_function,
        ),
        DiscoveredTaskFunction(
            file_path=Path("/project/tasks/sibling.py"),
            relative_path=Path("tasks/sibling.py"),
            name="successful_sibling",
            function=successful_sibling,
        ),
        DiscoveredAssetFunction(
            file_path=Path("/project/assets/intermediate.py"),
            relative_path=Path("assets/intermediate.py"),
            name="export_after_skip",
            function=export_after_skip,
            depends_on=(skip_function,),
        ),
        DiscoveredAssetFunction(
            file_path=Path("/project/assets/final.py"),
            relative_path=Path("assets/final.py"),
            name="export_after_mixed_skip",
            function=export_after_mixed_skip,
            depends_on=(export_after_skip, successful_sibling),
        ),
    )

    result: PythonNodeExecutorResult = execute_python_nodes(
        nodes=nodes,
        statement_recorder=StatementRecorder(),
        runtime=PythonNodeRuntime(
            adapter=PythonNodeContextTestAdapter(),
            connection_config={},
            connection=object(),
            run_id="test_run",
            target="dev",
            vars={},
            is_reload=False,
        ),
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
    ids=lambda case: case.description,
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
        statement_recorder=StatementRecorder(),
        runtime=PythonNodeRuntime(
            adapter=PythonNodeContextTestAdapter(),
            connection_config={},
            connection=object(),
            run_id="test_run",
            target="dev",
            vars={},
            is_reload=False,
        ),
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
    ids=lambda case: case.description,
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
        statement_recorder=StatementRecorder(),
        sleep=sleeps.append,
        runtime=PythonNodeRuntime(
            adapter=PythonNodeContextTestAdapter(),
            connection_config={},
            connection=object(),
            run_id="test_run",
            target="dev",
            vars={},
            is_reload=False,
        ),
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
    ids=lambda case: case.description,
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
        statement_recorder=StatementRecorder(),
        sleep=sleeps.append,
        runtime=PythonNodeRuntime(
            adapter=PythonNodeContextTestAdapter(),
            connection_config={},
            connection=object(),
            run_id="test_run",
            target="dev",
            vars={},
            is_reload=False,
        ),
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
    ids=lambda case: case.description,
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
        statement_recorder=StatementRecorder(),
        sleep=sleeps.append,
        runtime=PythonNodeRuntime(
            adapter=PythonNodeContextTestAdapter(),
            connection_config={},
            connection=object(),
            run_id="test_run",
            target="dev",
            vars={},
            is_reload=False,
        ),
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
    ids=lambda case: case.description,
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
        statement_recorder=StatementRecorder(),
        sleep=sleeps.append,
        runtime=PythonNodeRuntime(
            adapter=PythonNodeContextTestAdapter(),
            connection_config={},
            connection=object(),
            run_id="test_run",
            target="dev",
            vars={},
            is_reload=False,
        ),
    )

    assert result.results[0].status == test_case.expected_status
    assert result.results[0].payload == test_case.expected_payload
    assert result.results[0].error_message == test_case.expected_error_fragment
    assert flaky_task.attempts == test_case.expected_attempts
    assert tuple(sleeps) == test_case.expected_sleeps
