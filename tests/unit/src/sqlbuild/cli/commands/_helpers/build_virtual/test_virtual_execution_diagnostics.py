"""Virtual execution callback finalization tests."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from sqlbuild.cli.commands.classes.virtual_build_plan_hook import VirtualBuildPlanHook
from sqlbuild.cli.commands.models import VirtualBuildExecution
from tests.unit.src.sqlbuild.cli.commands._helpers.build_virtual._test_types import (
    VirtualCallbackCloseTestCase,
)
from tests.unit.src.sqlbuild.cli.commands._helpers.build_virtual.helpers import (
    build_high_volume_virtual_hook,
    emit_high_volume_virtual_diagnostics,
    execute_patched_virtual_build,
    patch_virtual_execution,
)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualCallbackCloseTestCase(
            description="successful virtual build closes callbacks and emits bounded summaries",
            error_type=RuntimeError,
            expected_scheduler_omitted=2,
            expected_query_omitted=2,
            expected_final_query_id="virtual-query-26",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_high_volume_success_when_virtual_build_finishes_then_callbacks_close_once(
    test_case: VirtualCallbackCloseTestCase,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    hook, callbacks = build_high_volume_virtual_hook()
    result: Mock = Mock()

    def succeed(**_kwargs: object) -> Mock:
        emit_high_volume_virtual_diagnostics(hook)
        return result

    patch_virtual_execution(monkeypatch=monkeypatch, hook=hook, pipeline=Mock(side_effect=succeed))

    execution: VirtualBuildExecution = execute_patched_virtual_build()
    hook.close()

    output: str = capsys.readouterr().out
    assert execution.result is result
    assert callbacks.close_calls == 1
    assert f"Scheduler diagnostics  {test_case.expected_scheduler_omitted}" in output
    assert f"Query diagnostics  {test_case.expected_query_omitted}" in output
    assert test_case.expected_final_query_id in output


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualCallbackCloseTestCase(
            description="failed virtual build closes callbacks and preserves failure",
            error_type=RuntimeError,
            expected_scheduler_omitted=2,
            expected_query_omitted=2,
            expected_final_query_id="virtual-query-26",
        ),
        VirtualCallbackCloseTestCase(
            description="interrupted virtual build closes callbacks and preserves interruption",
            error_type=KeyboardInterrupt,
            expected_scheduler_omitted=2,
            expected_query_omitted=2,
            expected_final_query_id="virtual-query-26",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_high_volume_error_when_virtual_build_unwinds_then_callbacks_close_once(
    test_case: VirtualCallbackCloseTestCase,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    hook: VirtualBuildPlanHook
    hook, callbacks = build_high_volume_virtual_hook()

    def fail(**_kwargs: object) -> None:
        emit_high_volume_virtual_diagnostics(hook)
        raise test_case.error_type("original virtual outcome")

    patch_virtual_execution(monkeypatch=monkeypatch, hook=hook, pipeline=Mock(side_effect=fail))

    with pytest.raises(test_case.error_type, match="original virtual outcome"):
        execute_patched_virtual_build()
    hook.close()

    output: str = capsys.readouterr().out
    assert callbacks.close_calls == 1
    assert f"Scheduler diagnostics  {test_case.expected_scheduler_omitted}" in output
    assert f"Query diagnostics  {test_case.expected_query_omitted}" in output
    assert test_case.expected_final_query_id in output


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualCallbackCloseTestCase(
            description="callback close failure is attempted once and does not escape",
            error_type=RuntimeError,
            expected_scheduler_omitted=0,
            expected_query_omitted=0,
            expected_final_query_id="",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_callback_close_failure_when_closing_hook_then_failure_is_non_degrading(
    test_case: VirtualCallbackCloseTestCase,
) -> None:
    close: Mock = Mock(side_effect=test_case.error_type("close failed"))
    callbacks: Mock = Mock(close=close)
    hook: VirtualBuildPlanHook = object.__new__(VirtualBuildPlanHook)
    hook.callbacks = callbacks
    hook._closed = False

    hook.close()
    hook.close()

    assert close.call_count == test_case.expected_scheduler_omitted + 1
