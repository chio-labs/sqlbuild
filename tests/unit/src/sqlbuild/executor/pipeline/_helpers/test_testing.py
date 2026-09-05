"""Tests for SQL unit test pipeline helpers."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models import (
    CompiledObjectKey,
    CompiledRelationLocation,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import ChainStep, PlanOutput, SqlTestPlanEntry
from sqlbuild.executor.pipeline._helpers import testing as testing_pipeline
from sqlbuild.executor.pipeline._helpers.testing import run_test_pipeline
from sqlbuild.executor.pipeline.models import TestPipelineCallbacks as PipelineCallbacks
from sqlbuild.executor.testing.models import SqlTestExecutionResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from sqlbuild.observability import (
    EventDispatcher,
    LifecycleEvent,
    dispatcher_scope,
    invocation_scope,
)
from tests.unit.src.sqlbuild.executor.pipeline._helpers._test_types import (
    SqlTestConcurrencyTestCase,
    SqlTestFunctionPreflightTestCase,
    SqlTestOperationLifecycleTestCase,
)
from tests.unit.src.sqlbuild.executor.pipeline._helpers.helpers import (
    lifecycle_events_with_prefix,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlTestFunctionPreflightTestCase(
            description="missing project function fails before running SQL test",
            expected_outcome="error",
            expected_error_fragment="Run `sqb build` first",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sql_test_with_missing_function_when_running_pipeline_then_returns_setup_error(
    test_case: SqlTestFunctionPreflightTestCase,
    tmp_path: Path,
) -> None:
    function_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.UDF,
        name="missing_function",
    )
    plan: PlanOutput = PlanOutput(
        test_entries=(
            SqlTestPlanEntry(
                key=CompiledObjectKey(
                    resource_type=CompiledResourceType.SQL_TEST,
                    name="test_missing_function",
                ),
                name="test_missing_function",
                chain=(
                    ChainStep(
                        model_name="fact_orders",
                        resolved_sql="SELECT main.missing_function(1) AS value",
                        expected_cte_sql="SELECT 2 AS value",
                    ),
                ),
                function_deps=(function_key,),
            ),
        ),
        function_locations={
            "missing_function": CompiledRelationLocation(
                database=None,
                schema="main",
                name="missing_function",
                qualified_name="main.missing_function",
            )
        },
    )
    order: list[str] = []
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()

    def record_event(event: LifecycleEvent) -> None:
        events.append(event)
        order.append(event.event_type)

    dispatcher.subscribe_lifecycle(subscriber=record_event, accepts_opaque=False)

    with invocation_scope("test-invocation"), dispatcher_scope(dispatcher):
        results: tuple[SqlTestExecutionResult, ...] = run_test_pipeline(
            plan=plan,
            connection_config={"database": str(tmp_path / "test.duckdb")},
            adapter=DuckDbAdapter(),
            callbacks=PipelineCallbacks(
                on_test_start=lambda _entry: order.append("callback_start"),
                on_test_complete=lambda _result: order.append("callback_complete"),
            ),
            run_id="test-run",
        )

    assert len(results) == 1
    assert results[0].outcome == test_case.expected_outcome
    assert results[0].error_message is not None
    assert test_case.expected_error_fragment in results[0].error_message
    lifecycle_order: tuple[str, ...] = tuple(
        filter(
            lambda value: value.startswith("resource_attempt_") or value.startswith("callback_"),
            order,
        )
    )
    assert lifecycle_order == (
        "resource_attempt_started",
        "callback_start",
        "resource_attempt_failed",
        "callback_complete",
    )
    resource_events: tuple[LifecycleEvent, ...] = tuple(
        filter(lambda event: event.event_type.startswith("resource_attempt_"), events)
    )
    assert tuple(event.run_id for event in resource_events) == ("test-run", "test-run")
    assert tuple(event.resource_id for event in resource_events) == (
        "sql_test:test_missing_function",
        "sql_test:test_missing_function",
    )


@pytest.mark.parametrize(
    "test_case",
    (
        SqlTestOperationLifecycleTestCase(
            description="parameterized chained test keeps one assertion operation and exact identity",
            expected_resource_id="sql_test:tests/unit/orders.sql:2:large_order",
            expected_operation_name="sql_test_assertion",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_parameterized_chain_when_running_then_one_operation_owns_statement_evaluation(
    tmp_path: Path,
    test_case: SqlTestOperationLifecycleTestCase,
) -> None:
    test_entry: SqlTestPlanEntry = SqlTestPlanEntry(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.SQL_TEST,
            name="test_orders__large_order",
        ),
        name="test_orders__large_order",
        source_path=Path("tests/unit/orders.sql"),
        block_index=2,
        case_name="large_order",
        chain=(
            ChainStep(
                model_name="orders",
                resolved_sql="SELECT 1 AS order_id",
                expected_cte_sql="SELECT 1 AS order_id",
            ),
        ),
    )
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)

    with invocation_scope("test-invocation"), dispatcher_scope(dispatcher):
        results: tuple[SqlTestExecutionResult, ...] = run_test_pipeline(
            plan=PlanOutput(test_entries=(test_entry,)),
            connection_config={"database": str(tmp_path / "test.duckdb")},
            adapter=DuckDbAdapter(),
            run_id="test-run",
        )

    event_types: tuple[str, ...] = tuple(event.event_type for event in events)
    assert results[0].outcome == "pass"
    assert event_types == (
        "resource_attempt_started",
        "operation_started",
        "statement_started",
        "statement_completed",
        "operation_completed",
        "resource_attempt_completed",
    )
    assert all(event.resource_id == test_case.expected_resource_id for event in events)
    operation_events: tuple[LifecycleEvent, ...] = lifecycle_events_with_prefix(
        events=events, prefixes=("operation_",)
    )
    statement_events: tuple[LifecycleEvent, ...] = lifecycle_events_with_prefix(
        events=events, prefixes=("statement_",)
    )
    assert len(operation_events) == 2
    assert operation_events[0].payload["operation_name"] == test_case.expected_operation_name
    assert all(event.operation_id == operation_events[0].operation_id for event in statement_events)
    assert all(
        event.resource_attempt_id == operation_events[0].resource_attempt_id for event in events
    )


@pytest.mark.parametrize(
    "test_case",
    (
        SqlTestConcurrencyTestCase(
            description="two workers overlap using isolated connections",
            test_count=2,
            max_concurrency=2,
            expected_connection_count=2,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_concurrent_workers_when_running_tests_then_execution_overlaps_on_isolated_connections(
    test_case: SqlTestConcurrencyTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entries: tuple[SqlTestPlanEntry, ...] = tuple(
        SqlTestPlanEntry(
            key=CompiledObjectKey(
                resource_type=CompiledResourceType.SQL_TEST,
                name=f"test_{index}",
            ),
            name=f"test_{index}",
            chain=(
                ChainStep(
                    model_name=f"model_{index}",
                    resolved_sql=f"SELECT {index} AS value",
                    expected_cte_sql=f"SELECT {index} AS value",
                ),
            ),
        )
        for index in range(test_case.test_count)
    )
    overlap_barrier: threading.Barrier = threading.Barrier(test_case.expected_connection_count)
    connection_ids: list[int] = []
    connection_ids_lock: threading.Lock = threading.Lock()

    def execute_with_overlap(
        *, test_entry: SqlTestPlanEntry, adapter: DuckDbAdapter, connection: object
    ) -> SqlTestExecutionResult:
        del adapter
        with connection_ids_lock:
            connection_ids.append(id(connection))
        overlap_barrier.wait(timeout=2)
        return SqlTestExecutionResult(
            test_name=test_entry.name,
            outcome=SqlTestOutcome.PASS,
        )

    monkeypatch.setattr(testing_pipeline, "execute_sql_test", execute_with_overlap)
    completed_names: list[str] = []
    started_names: list[str] = []

    results: tuple[SqlTestExecutionResult, ...] = run_test_pipeline(
        plan=PlanOutput(test_entries=entries),
        connection_config={"database": str(tmp_path / "test.duckdb")},
        adapter=DuckDbAdapter(),
        max_concurrency=test_case.max_concurrency,
        callbacks=PipelineCallbacks(
            on_test_start=lambda entry: started_names.append(entry.name),
            on_test_complete=lambda result: completed_names.append(result.test_name),
        ),
    )

    expected_names: tuple[str, ...] = tuple(
        f"test_{index}" for index in range(test_case.test_count)
    )
    assert tuple(result.test_name for result in results) == expected_names
    assert started_names == list(expected_names)
    assert completed_names == list(expected_names)
    assert len(set(connection_ids)) == test_case.expected_connection_count
