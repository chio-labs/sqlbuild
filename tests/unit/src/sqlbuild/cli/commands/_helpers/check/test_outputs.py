"""Tests for canonical Python check terminal projection."""

from __future__ import annotations

from contextvars import Token
from io import StringIO
from types import SimpleNamespace
from typing import Any, cast

import pytest

import sqlbuild.cli.commands._helpers.check.execution as check_execution
from sqlbuild.cli.commands._helpers.check.core import write_check_results
from sqlbuild.cli.commands._helpers.check.execution import execute_check_plan
from sqlbuild.cli.commands.models import CheckExecutionPreparation, CheckInvocation
from sqlbuild.cli.progress.classes.native_progress_projector import NativeProgressProjector
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.executor.python_nodes.classes.run_state import PythonNodeRunState
from sqlbuild.executor.python_nodes.models import (
    PythonCheckExecutionResult,
    PythonIngressLoaderExecutorResult,
)
from sqlbuild.observability import (
    EventDispatcher,
    ResourceAttemptLifecycle,
    dispatcher_scope,
    invocation_scope,
)
from tests.unit.src.sqlbuild.cli.commands._helpers.check._test_types import (
    CheckOutputProjectionCase,
)
from tests.unit.src.sqlbuild.cli.commands._helpers.check.helpers import (
    check_results,
    publish_check_attempt,
)


class _FailBeforeSecondCheckStream(StringIO):
    def write(self, text: str) -> int:
        if text.startswith("  check     second") and "PASS" in text:
            raise OSError("controlled check output failure")
        return super().write(text)


class _CloseFailingAdapter:
    def connect(self, connection_config: dict[str, object]) -> object:
        return connection_config

    def close(self, connection: object) -> None:
        del connection
        raise OSError("controlled adapter close failure")


@pytest.mark.parametrize(
    "test_case",
    (
        CheckOutputProjectionCase(
            description="normal grouped output claims canonical durations without duplicates",
            expected_first_duration="0.10s",
            expected_second_duration="0.20s",
            expected_generic_terminal_count=0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_completed_checks_when_grouped_rows_render_then_terminals_are_claimed_once(
    test_case: CheckOutputProjectionCase,
) -> None:
    stream: StringIO = StringIO()
    projector: NativeProgressProjector = NativeProgressProjector(stream=stream, use_color=False)
    projector.configure_resources(ordinals={"first": 1, "second": 2}, total=2)
    publish_check_attempt(projector=projector, name="first", duration_ms=100)
    publish_check_attempt(projector=projector, name="second", duration_ms=200)
    token: Token[NativeProgressProjector | None] = projector.install()
    try:
        write_check_results(stream=stream, results=check_results(), use_color=False)
    finally:
        projector.restore(token)
    projector.close()
    output: str = stream.getvalue()

    assert f"PASS  {test_case.expected_first_duration}" in output
    assert f"PASS  {test_case.expected_second_duration}" in output
    assert output.count("check     first OK") == test_case.expected_generic_terminal_count
    assert output.count("check     second OK") == test_case.expected_generic_terminal_count


@pytest.mark.parametrize(
    "test_case",
    (
        CheckOutputProjectionCase(
            description="failure before second row leaves only second terminal for close",
            expected_first_duration="0.10s",
            expected_second_duration="0.20s",
            expected_generic_terminal_count=1,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_two_completed_checks_when_second_row_fails_then_close_renders_unclaimed_terminal(
    test_case: CheckOutputProjectionCase,
) -> None:
    stream: _FailBeforeSecondCheckStream = _FailBeforeSecondCheckStream()
    projector: NativeProgressProjector = NativeProgressProjector(stream=stream, use_color=False)
    projector.configure_resources(ordinals={"first": 1, "second": 2}, total=2)
    publish_check_attempt(projector=projector, name="first", duration_ms=100)
    publish_check_attempt(projector=projector, name="second", duration_ms=200)
    token: Token[NativeProgressProjector | None] = projector.install()
    with pytest.raises(OSError, match="controlled check output failure"):
        write_check_results(stream=stream, results=check_results(), use_color=False)
    projector.restore(token)
    projector.close()
    output: str = stream.getvalue()

    assert test_case.expected_first_duration in output
    assert output.count("check     first OK") == 0
    assert output.count(f"check     second OK {test_case.expected_second_duration}") == (
        test_case.expected_generic_terminal_count
    )


@pytest.mark.parametrize(
    "test_case",
    (
        CheckOutputProjectionCase(
            description="adapter close failure leaves all executed check terminals unclaimed",
            expected_first_duration="0.00s",
            expected_second_duration="0.00s",
            expected_generic_terminal_count=2,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_checks_complete_when_adapter_close_fails_then_close_renders_all_terminals(
    monkeypatch: pytest.MonkeyPatch,
    test_case: CheckOutputProjectionCase,
) -> None:
    stream: StringIO = StringIO()
    projector: NativeProgressProjector = NativeProgressProjector(stream=stream, use_color=False)
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=projector.consume, accepts_opaque=False)
    run_state: PythonNodeRunState = PythonNodeRunState()
    ingress_result: PythonIngressLoaderExecutorResult = PythonIngressLoaderExecutorResult(
        python_results=(), load_results=(), run_state=run_state
    )
    monkeypatch.setattr(check_execution, "_execute_check_ingress", lambda **_: ingress_result)
    monkeypatch.setattr(check_execution, "_execute_check_read_side", lambda **_: ())

    def execute_checks(**_: Any) -> tuple[PythonCheckExecutionResult, ...]:
        with ResourceAttemptLifecycle(
            resource_id="check:first",
            resource_kind="check",
            resource_name="first",
            run_id="check-run",
        ):
            pass
        with ResourceAttemptLifecycle(
            resource_id="check:second",
            resource_kind="check",
            resource_name="second",
            run_id="check-run",
        ):
            pass
        return check_results()

    monkeypatch.setattr(check_execution, "execute_python_checks", execute_checks)
    invocation: CheckInvocation = cast(
        CheckInvocation,
        SimpleNamespace(
            adapter=_CloseFailingAdapter(),
            connection_config={},
            use_color=False,
        ),
    )
    preparation: CheckExecutionPreparation = cast(
        CheckExecutionPreparation,
        SimpleNamespace(
            check_functions=(SimpleNamespace(name="first"), SimpleNamespace(name="second")),
            python_graph=object(),
            lifecycle_plan=object(),
            relation_targets={},
            default_database=None,
            default_schema=None,
        ),
    )
    pipeline_result: CompilePipelineResult = cast(
        CompilePipelineResult,
        SimpleNamespace(
            project=SimpleNamespace(
                run_id="check-run", effective_target_name=None, effective_vars={}
            ),
            plan_output=SimpleNamespace(source_map={}),
        ),
    )
    token: Token[NativeProgressProjector | None] = projector.install()
    with invocation_scope("check-invocation"), dispatcher_scope(dispatcher):
        with pytest.raises(OSError, match="controlled adapter close failure"):
            execute_check_plan(
                invocation=invocation,
                pipeline_result=pipeline_result,
                preparation=preparation,
                providers=cast(Any, None),
            )
    projector.restore(token)
    projector.close()
    output: str = stream.getvalue()

    assert output.count("check     first OK") == 1
    assert output.count("check     second OK") == 1
    assert output.count(" OK ") == test_case.expected_generic_terminal_count
