from __future__ import annotations

from contextvars import Token
from dataclasses import replace
from io import StringIO
from pathlib import Path

import pytest

from sqlbuild.cli.commands.classes.build_progress_callbacks import BuildProgressCallbacks
from sqlbuild.cli.output.classes.terminal_event_index import (
    TerminalEventIndex,
    terminal_event_index_scope,
)
from sqlbuild.cli.progress.classes.native_progress_projector import NativeProgressProjector
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import ChainStep, PlanOutput, SqlTestPlanEntry
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.executor.testing.models import SqlTestExecutionResult, StepResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from sqlbuild.runtime.observability.models import LifecycleEvent
from tests.unit.src.sqlbuild.cli.progress.classes._test_types import BuildSqlTestProjectionCase
from tests.unit.src.sqlbuild.runtime.observability.helpers import lifecycle_event


@pytest.mark.parametrize(
    "test_case",
    (
        BuildSqlTestProjectionCase(
            description="passing build test remains grouped under model",
            expected_status="PASS",
            expected_status_count=2,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_passing_build_test_when_canonical_terminal_arrives_then_grouped_row_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
    test_case: BuildSqlTestProjectionCase,
) -> None:
    stream: StringIO = StringIO()
    monkeypatch.setattr("sys.stdout", stream)
    projector: NativeProgressProjector = NativeProgressProjector(stream=stream, use_color=False)
    token: Token[NativeProgressProjector | None] = projector.install()
    test_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.SQL_TEST, name="test_orders"
    )
    model_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.MODEL, name="orders"
    )
    callbacks: BuildProgressCallbacks = BuildProgressCallbacks(
        plan=PlanOutput(
            execution_order=(test_key, model_key),
            test_entries=(
                SqlTestPlanEntry(
                    key=test_key,
                    name="test_orders",
                    chain=(ChainStep(model_name="orders", resolved_sql="SELECT 1"),),
                ),
            ),
        ),
        use_color=False,
    )
    test_start: LifecycleEvent = replace(
        lifecycle_event(
            "resource_attempt_started",
            run_id="run",
            resource_id="sql_test:test_orders",
            resource_attempt_id="test-attempt",
            payload={
                "resource_kind": "test",
                "resource_name": "test_orders",
                "attempt_number": 1,
            },
        ),
        event_id="test-start",
    )
    model_start: LifecycleEvent = replace(
        test_start,
        event_id="model-start",
        resource_id="model:orders",
        resource_attempt_id="model-attempt",
        payload={
            "resource_kind": "table",
            "resource_name": "orders",
            "attempt_number": 1,
        },
    )
    try:
        projector.consume(test_start)
        projector.consume(
            replace(
                test_start,
                event_id="test-terminal",
                event_type="resource_attempt_completed",
                payload={**test_start.payload, "duration_ms": 20.0},
            )
        )
        callbacks.on_node_complete(
            SqlTestExecutionResult(
                test_name="test_orders",
                outcome=SqlTestOutcome.PASS,
                step_results=(StepResult(model_name="orders", outcome=SqlTestOutcome.PASS),),
            )
        )
        projector.consume(model_start)
        projector.consume(
            replace(
                model_start,
                event_id="model-terminal",
                event_type="resource_attempt_completed",
                payload={**model_start.payload, "duration_ms": 30.0},
            )
        )
        callbacks.on_node_complete(
            ModelExecutionResult(model_name="orders", status=ExecutionStatus.SUCCESS)
        )
        callbacks.close()
        projector.close()
    finally:
        projector.restore(token)

    output: str = stream.getvalue()
    assert output.count(test_case.expected_status) == test_case.expected_status_count
    assert "test      test_orders" in output
    assert "test      test_orders OK" not in output


@pytest.mark.parametrize(
    "test_case",
    (
        BuildSqlTestProjectionCase(
            description="failing build test emits one rich row and execution event",
            expected_status="ERROR",
            expected_status_count=2,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_failing_build_test_when_canonical_terminal_arrives_then_rich_row_and_event_remain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    test_case: BuildSqlTestProjectionCase,
) -> None:
    stream: StringIO = StringIO()
    monkeypatch.setattr("sys.stderr", stream)
    projector: NativeProgressProjector = NativeProgressProjector(stream=stream, use_color=False)
    token: Token[NativeProgressProjector | None] = projector.install()
    terminal_index: TerminalEventIndex = TerminalEventIndex()
    event_path: Path = tmp_path / "events.jsonl"
    test_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.SQL_TEST, name="test_orders"
    )
    start: LifecycleEvent = replace(
        lifecycle_event(
            "resource_attempt_started",
            run_id="run",
            resource_id="sql_test:test_orders",
            resource_attempt_id="test-attempt",
            payload={
                "resource_kind": "test",
                "resource_name": "test_orders",
                "attempt_number": 1,
            },
        ),
        event_id="test-start",
    )
    try:
        with terminal_event_index_scope(terminal_index):
            callbacks: BuildProgressCallbacks = BuildProgressCallbacks(
                plan=PlanOutput(
                    execution_order=(test_key,),
                    test_entries=(SqlTestPlanEntry(key=test_key, name="test_orders"),),
                ),
                use_color=False,
                event_output_path=event_path,
            )
            projector.consume(start)
            terminal_index.consume(start)
            terminal: LifecycleEvent = replace(
                start,
                event_id="test-terminal",
                event_type="resource_attempt_failed",
                payload={
                    **start.payload,
                    "duration_ms": 40.0,
                    "error_type": "TestExecutionError",
                },
            )
            projector.consume(terminal)
            terminal_index.consume(terminal)
            callbacks.on_node_complete(
                SqlTestExecutionResult(
                    test_name="test_orders",
                    outcome=SqlTestOutcome.ERROR,
                    step_results=(StepResult(model_name="orders", outcome=SqlTestOutcome.ERROR),),
                    error_code="T001",
                    error_message="controlled test failure",
                )
            )
            callbacks.close()
        projector.close()
    finally:
        projector.restore(token)

    output: str = stream.getvalue()
    assert output.count(test_case.expected_status) == test_case.expected_status_count
    assert "controlled test failure" in output
    assert "test      test_orders FAIL" not in output
    assert "test_orders" in event_path.read_text(encoding="utf-8")
