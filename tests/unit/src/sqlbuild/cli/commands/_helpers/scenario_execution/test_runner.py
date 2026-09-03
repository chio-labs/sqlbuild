from __future__ import annotations

from contextvars import Token
from typing import Any, cast
from unittest.mock import Mock

import pytest

from sqlbuild.cli.commands._helpers.scenario_execution import runner
from sqlbuild.cli.commands.models import ScenarioTestCommandRequest
from sqlbuild.cli.progress.classes.native_progress_projector import NativeProgressProjector
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.observability import EventDispatcher, LifecycleEvent, dispatcher_scope
from tests.unit.src.sqlbuild.cli.commands._helpers.scenario_execution._test_types import (
    ScenarioCompilePresentationTestCase,
)
from tests.unit.src.sqlbuild.cli.commands._helpers.scenario_execution.helpers import (
    ScenarioProgressStream,
    configure_scenario_runner,
)


@pytest.mark.parametrize(
    "test_case",
    (
        ScenarioCompilePresentationTestCase(
            "non-tty canonical compile owns rows",
            False,
            "Project compile  START",
            "Compiling project...",
            "operation_completed",
        ),
        ScenarioCompilePresentationTestCase(
            "tty planning spinner owns rows",
            True,
            "Compiled project.",
            "Project compile  START",
            "operation_completed",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_scenario_compile_when_running_then_presentation_has_one_owner(
    monkeypatch: pytest.MonkeyPatch,
    test_case: ScenarioCompilePresentationTestCase,
) -> None:
    stream: ScenarioProgressStream = ScenarioProgressStream(tty=test_case.tty)
    pipeline_result: Mock = Mock()
    pipeline_result.project.sql_scenarios = ()

    def compile_project(**kwargs: Any) -> CompilePipelineResult:
        on_progress: Any = kwargs["on_progress"]
        on_progress("Compiling project...")
        on_progress("Compiled project.")
        return cast(CompilePipelineResult, pipeline_result)

    configure_scenario_runner(
        monkeypatch=monkeypatch, stream=stream, compile_project=compile_project
    )
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    projector: NativeProgressProjector = NativeProgressProjector(stream=stream, use_color=False)
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)
    dispatcher.subscribe_lifecycle(subscriber=projector.consume, accepts_opaque=False)
    token: Token[NativeProgressProjector | None] = projector.install()

    try:
        with dispatcher_scope(dispatcher):
            exit_code: int = runner.run_scenario(ScenarioTestCommandRequest())
    finally:
        projector.restore(token)

    assert exit_code == 0
    assert test_case.expected_fragment in stream.getvalue()
    assert test_case.unexpected_fragment not in stream.getvalue()
    assert tuple(event.event_type for event in events[-2:]) == (
        "operation_started",
        test_case.expected_terminal,
    )


@pytest.mark.parametrize(
    "test_case",
    (
        ScenarioCompilePresentationTestCase(
            "non-tty compile failure",
            False,
            "Project compile  FAIL",
            "Compiled project.",
            "operation_failed",
        ),
        ScenarioCompilePresentationTestCase(
            "tty compile failure cleans spinner",
            True,
            "",
            "Project compile  START",
            "operation_failed",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_scenario_compile_failure_when_running_then_lifecycle_fails_and_progress_closes(
    monkeypatch: pytest.MonkeyPatch,
    test_case: ScenarioCompilePresentationTestCase,
) -> None:
    stream: ScenarioProgressStream = ScenarioProgressStream(tty=test_case.tty)

    def fail_compile(**kwargs: Any) -> CompilePipelineResult:
        on_progress: Any = kwargs["on_progress"]
        on_progress("Compiling project...")
        raise RuntimeError("compile failed")

    configure_scenario_runner(monkeypatch=monkeypatch, stream=stream, compile_project=fail_compile)
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    projector: NativeProgressProjector = NativeProgressProjector(stream=stream, use_color=False)
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)
    dispatcher.subscribe_lifecycle(subscriber=projector.consume, accepts_opaque=False)
    token: Token[NativeProgressProjector | None] = projector.install()

    try:
        with dispatcher_scope(dispatcher):
            with pytest.raises(RuntimeError, match="compile failed"):
                runner.run_scenario(ScenarioTestCommandRequest())
    finally:
        projector.restore(token)

    assert test_case.expected_fragment in stream.getvalue()
    assert test_case.unexpected_fragment not in stream.getvalue()
    assert tuple(event.event_type for event in events[-2:]) == (
        "operation_started",
        test_case.expected_terminal,
    )
