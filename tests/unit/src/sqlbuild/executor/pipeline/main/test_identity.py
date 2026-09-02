from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

import sqlbuild.executor.pipeline.main.run as run_module
from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.cost.classes.cost_context import CostContext
from sqlbuild.cost.models import CostResourceContext
from sqlbuild.executor.build.models import BuildExecutionResult, BuildRuntimeParams
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.observability import (
    EventDispatcher,
    ExecutionIdentity,
    LifecycleEvent,
    current_execution_identity,
    dispatcher_scope,
    invocation_scope,
)
from sqlbuild.spec.contracts.models import SettingsConfig
from tests.unit.src.sqlbuild.executor.pipeline.main._test_types import (
    PipelineIdentityTestCase,
    RunTerminalTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PipelineIdentityTestCase(
            description="shared run boundary preserves SQLBuild run ID and outer invocation",
            expected_invocation_id="inv-outer",
            expected_run_id="SQLBuild Run / 001",
            expected_event_types=("run_started", "run_completed"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_outer_invocation_when_running_shared_pipeline_then_run_and_cost_contexts_are_scoped(
    test_case: PipelineIdentityTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_identities: list[ExecutionIdentity | None] = []
    observed_cost_contexts: list[CostResourceContext | None] = []
    expected_result: BuildExecutionResult = BuildExecutionResult(status=BuildStatus.SUCCESS)

    def execute_pipeline(**_kwargs: Any) -> BuildExecutionResult:
        observed_identities.append(current_execution_identity())
        observed_cost_contexts.append(CostContext.current())
        return expected_result

    monkeypatch.setattr(run_module, "_run_build_pipeline", execute_pipeline)
    runtime: BuildRuntimeParams = BuildRuntimeParams(
        run_id=test_case.expected_run_id,
        runtime_dir=Path("target"),
        target="dev",
    )
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    _ = dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)

    with dispatcher_scope(dispatcher):
        with invocation_scope(test_case.expected_invocation_id) as outer:
            result: BuildExecutionResult = run_module.run_build_pipeline(
                plan=PlanOutput(),
                connection_config={},
                adapter=Mock(spec=BaseAdapter),
                settings=Mock(spec=SettingsConfig),
                runtime=runtime,
            )
            restored: ExecutionIdentity | None = current_execution_identity()

    assert result == expected_result
    assert observed_identities[0] is not None
    assert observed_identities[0].invocation_id == test_case.expected_invocation_id
    assert observed_identities[0].run_id == test_case.expected_run_id
    assert observed_cost_contexts[0] is not None
    assert observed_cost_contexts[0].run_id == test_case.expected_run_id
    assert tuple(event.event_type for event in events) == test_case.expected_event_types
    assert restored == outer
    assert current_execution_identity() is None


@pytest.mark.parametrize(
    "test_case",
    [
        RunTerminalTestCase(
            description="failed aggregate result emits counts",
            expected_event_type="run_failed",
            expected_error_type=None,
            expected_failed_count=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_failed_build_result_when_running_shared_pipeline_then_one_failed_terminal_has_counts(
    test_case: RunTerminalTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_result: BuildExecutionResult = BuildExecutionResult(
        status=BuildStatus.FAILED,
        success_count=1,
        failure_count=test_case.expected_failed_count or 0,
        skipped_count=3,
    )
    monkeypatch.setattr(run_module, "_run_build_pipeline", lambda **_kwargs: expected_result)
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    _ = dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)

    with dispatcher_scope(dispatcher):
        with invocation_scope("inv-failed"):
            result: BuildExecutionResult = run_module.run_build_pipeline(
                plan=PlanOutput(),
                connection_config={},
                adapter=Mock(spec=BaseAdapter),
                settings=Mock(spec=SettingsConfig),
                runtime=BuildRuntimeParams(
                    run_id="run-failed", runtime_dir=Path("target"), target="dev"
                ),
            )

    assert result == expected_result
    assert tuple(event.event_type for event in events) == (
        "run_started",
        test_case.expected_event_type,
    )
    assert events[-1].payload["failed_count"] == test_case.expected_failed_count


@pytest.mark.parametrize(
    "test_case",
    [
        RunTerminalTestCase(
            description="pipeline exception emits error type",
            expected_event_type="run_failed",
            expected_error_type="RuntimeError",
            expected_failed_count=None,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_pipeline_exception_when_running_shared_pipeline_then_one_failed_terminal_has_error_type(
    test_case: RunTerminalTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def execute_pipeline(**_kwargs: Any) -> BuildExecutionResult:
        raise RuntimeError("controlled pipeline exception")

    monkeypatch.setattr(run_module, "_run_build_pipeline", execute_pipeline)
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    _ = dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)

    with dispatcher_scope(dispatcher):
        with invocation_scope("inv-exception"):
            with pytest.raises(RuntimeError, match="controlled pipeline exception"):
                run_module.run_build_pipeline(
                    plan=PlanOutput(),
                    connection_config={},
                    adapter=Mock(spec=BaseAdapter),
                    settings=Mock(spec=SettingsConfig),
                    runtime=BuildRuntimeParams(
                        run_id="run-exception", runtime_dir=Path("target"), target="dev"
                    ),
                )

    assert tuple(event.event_type for event in events) == (
        "run_started",
        test_case.expected_event_type,
    )
    assert events[-1].payload["error_type"] == test_case.expected_error_type
