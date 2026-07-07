"""Tests for source loader DAG runtime helpers."""

from __future__ import annotations

import queue

import pytest

from sqlbuild.executor.load.helpers.dag_runtime import (
    build_load_dag_state,
    complete_dag_source,
    load_dag_worker,
)
from sqlbuild.executor.load.models import (
    LoadDagState,
    LoadDispatchInputs,
    LoadExecutionIndexes,
    LoadExecutionResult,
    LoadRuntimeParams,
)
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.spec.models.source import SourceEntry
from tests.unit.src.sqlbuild.executor.load._test_types import (
    LoadDagStateSchedulingTestCase,
    LoadDagWorkerFailureTestCase,
)
from tests.unit.src.sqlbuild.executor.load.helpers import LoaderContextTestAdapter


@pytest.mark.parametrize(
    "test_case",
    [
        LoadDagStateSchedulingTestCase(
            description="unlocks loader downstream source after upstream success completion",
            source_names=("fetch_orders", "raw_orders"),
            upstream_names={"fetch_orders": (), "raw_orders": ("fetch_orders",)},
            downstream_names={"fetch_orders": ("raw_orders",), "raw_orders": ()},
            completed_source_name="fetch_orders",
            expected_initial_ready=("fetch_orders",),
            expected_final_ready=("fetch_orders", "raw_orders"),
            expected_callback_sources=("fetch_orders",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_load_dag_state_when_completing_source_then_uses_generic_scheduler(
    test_case: LoadDagStateSchedulingTestCase,
) -> None:
    sources: tuple[SourceEntry, ...] = tuple(
        SourceEntry(name=source_name, loader=f"{source_name}_loader")
        for source_name in test_case.source_names
    )
    results: list[LoadExecutionResult | None] = [None] * len(sources)
    completed_results: list[LoadExecutionResult] = []
    state: LoadDagState = build_load_dag_state(
        sources=sources,
        results=results,
        source_index_by_name={source.name: index for index, source in enumerate(sources)},
        upstream_names=test_case.upstream_names,
        downstream_names=test_case.downstream_names,
    )

    assert tuple(state.ready) == test_case.expected_initial_ready

    result: LoadExecutionResult = LoadExecutionResult(
        source_name=test_case.completed_source_name,
        loader_name=f"{test_case.completed_source_name}_loader",
        status=ExecutionStatus.SUCCESS,
        target=test_case.completed_source_name,
    )
    complete_dag_source(
        source_name=test_case.completed_source_name,
        result=result,
        state=state,
        on_load_complete=completed_results.append,
    )

    assert tuple(state.ready) == test_case.expected_final_ready
    assert tuple(completed.source_name for completed in completed_results) == (
        test_case.expected_callback_sources
    )
    assert results[0] == result


@pytest.mark.parametrize(
    "test_case",
    [
        LoadDagWorkerFailureTestCase(
            description="publishes failed completion when ready source execution raises",
            source_name="raw_orders",
            loader_name="missing_loader",
            expected_status=ExecutionStatus.FAILED,
            expected_error_fragment="missing_loader",
        ),
        LoadDagWorkerFailureTestCase(
            description="returns connection when ready source execution raises",
            source_name="raw_customers",
            loader_name="missing_customer_loader",
            expected_status=ExecutionStatus.FAILED,
            expected_error_fragment="missing_customer_loader",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_ready_source_execution_raises_when_worker_runs_then_publishes_failed_completion(
    test_case: LoadDagWorkerFailureTestCase,
) -> None:
    connection: object = object()
    connection_pool: queue.Queue[object] = queue.Queue()
    connection_pool.put(connection)
    completion_queue: queue.Queue[tuple[str, LoadExecutionResult]] = queue.Queue()
    source_entry: SourceEntry = SourceEntry(
        name=test_case.source_name,
        loader=test_case.loader_name,
    )

    load_dag_worker(
        source_name=test_case.source_name,
        dispatch=LoadDispatchInputs(
            source_by_name={test_case.source_name: source_entry},
            indexes=LoadExecutionIndexes(
                loader_by_name={},
                source_by_name={test_case.source_name: source_entry},
                source_by_loader_name={},
                loader_ref_entries={},
                loader_name_by_function={},
                has_loader_dependencies=False,
            ),
            failed_or_hard_skipped=set(),
            results_by_name={},
        ),
        adapter=LoaderContextTestAdapter(),
        connection_config={},
        connection_pool=connection_pool,
        runtime=LoadRuntimeParams(
            run_id="run-1",
            target=None,
            vars={},
            is_reload=False,
        ),
        completion_queue=completion_queue,
    )

    completed_source_name, result = completion_queue.get_nowait()

    assert completed_source_name == test_case.source_name
    assert result.source_name == test_case.source_name
    assert result.loader_name == test_case.loader_name
    assert result.status == test_case.expected_status
    assert result.error_message is not None
    assert test_case.expected_error_fragment in result.error_message
    assert connection_pool.get_nowait() is connection
