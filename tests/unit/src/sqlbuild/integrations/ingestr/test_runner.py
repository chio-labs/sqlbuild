"""Canonical subprocess lifecycle tests for ingestr."""

from __future__ import annotations

import subprocess

import pytest

from sqlbuild.integrations.ingestr._helpers.runner import run_ingestr_command
from sqlbuild.integrations.ingestr.exceptions import IngestrIntegrationError
from sqlbuild.observability import (
    EventDispatcher,
    LifecycleEvent,
    dispatcher_scope,
    invocation_scope,
)
from tests.unit.src.sqlbuild.integrations.ingestr._test_types import IngestrRunnerTestCase


@pytest.mark.parametrize(
    "test_case",
    (
        IngestrRunnerTestCase(
            description="signalled child excludes streams and arguments",
            returncode=-15,
            expected_signal_number=15,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_signalled_ingestr_when_run_then_safe_terminal_excludes_child_streams(
    test_case: IngestrRunnerTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)
    monkeypatch.setattr(
        "sqlbuild.integrations.ingestr._helpers.runner.shutil.which",
        lambda executable: executable,
    )
    monkeypatch.setattr(
        "sqlbuild.integrations.ingestr._helpers.runner._run_ingestr_subprocess",
        lambda **kwargs: subprocess.CompletedProcess(
            args=kwargs["command"],
            returncode=test_case.returncode,
            stdout="private child stdout",
            stderr="private child stderr",
        ),
    )

    with (
        invocation_scope("inv-ingestr-signal"),
        dispatcher_scope(dispatcher),
        pytest.raises(IngestrIntegrationError, match=f"exit code {test_case.returncode}"),
    ):
        _ = run_ingestr_command(("ingestr", "--secret", "private-value"))

    assert tuple(event.event_type for event in events) == (
        "operation_started",
        "operation_failed",
    )
    assert events[0].payload == {
        "operation_kind": "subprocess",
        "operation_name": "ingestr_command",
    }
    assert events[1].payload["exit_code"] == test_case.returncode
    assert events[1].payload["signal_number"] == test_case.expected_signal_number
    assert "private" not in repr(events)


@pytest.mark.parametrize(
    "test_case",
    (
        IngestrRunnerTestCase(
            description="interrupted child has no fabricated terminal",
            returncode=0,
            expected_signal_number=0,
            expected_event_types=("operation_started",),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_unobserved_ingestr_interruption_when_run_then_only_start_is_published(
    test_case: IngestrRunnerTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)
    monkeypatch.setattr(
        "sqlbuild.integrations.ingestr._helpers.runner.shutil.which",
        lambda executable: executable,
    )
    monkeypatch.setattr(
        "sqlbuild.integrations.ingestr._helpers.runner._run_ingestr_subprocess",
        lambda **kwargs: (_ for _ in ()).throw(KeyboardInterrupt),
    )

    with (
        invocation_scope(f"inv-{test_case.description}"),
        dispatcher_scope(dispatcher),
        pytest.raises(KeyboardInterrupt),
    ):
        _ = run_ingestr_command(("ingestr", "run"))

    assert tuple(event.event_type for event in events) == test_case.expected_event_types
