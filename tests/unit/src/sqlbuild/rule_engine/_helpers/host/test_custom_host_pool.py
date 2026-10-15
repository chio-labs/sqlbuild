"""The custom-rule host waits for its payload only while the parent still wants it."""

import time
from pathlib import Path

import pytest

from sqlbuild.rule_engine._helpers.host import custom_host
from sqlbuild.rule_engine.exceptions import HostCancelledError, RulesError
from tests.unit.src.sqlbuild.rule_engine._helpers.host._test_types import (
    AwaitInputsTestCase,
    AwaitPublishedInputsTestCase,
)
from tests.unit.src.sqlbuild.rule_engine._helpers.host.helpers import touch_files


@pytest.mark.parametrize(
    "test_case",
    (
        AwaitInputsTestCase(
            description="parent exited before publishing",
            reported_parent_pid=1,
            existing_files=(),
            expected_error=RulesError,
            expected_max_seconds=1.0,
        ),
        AwaitInputsTestCase(
            description="run abandoned by its parent",
            reported_parent_pid=4242,
            existing_files=("project.abandoned",),
            expected_error=HostCancelledError,
            expected_max_seconds=1.0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_waiting_host_when_parent_exits_or_run_is_abandoned_then_wait_stops_promptly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, test_case: AwaitInputsTestCase
) -> None:
    touch_files(root=tmp_path, names=test_case.existing_files)
    monkeypatch.setattr(custom_host.os, "getppid", lambda: test_case.reported_parent_pid)
    started: float = time.monotonic()

    with pytest.raises(test_case.expected_error):
        custom_host.await_inputs(
            path=tmp_path / "project.pickle",
            cancel_markers=(tmp_path / "project.abandoned",),
            parent_pid=4242,
        )

    assert time.monotonic() - started < test_case.expected_max_seconds


@pytest.mark.parametrize(
    "test_case",
    (
        AwaitPublishedInputsTestCase(
            description="payload published while the parent runs",
            reported_parent_pid=4242,
            existing_files=("project.pickle",),
            expected_max_seconds=1.0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_published_payload_when_parent_still_runs_then_wait_returns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, test_case: AwaitPublishedInputsTestCase
) -> None:
    touch_files(root=tmp_path, names=test_case.existing_files)
    monkeypatch.setattr(custom_host.os, "getppid", lambda: test_case.reported_parent_pid)
    started: float = time.monotonic()

    custom_host.await_inputs(
        path=tmp_path / "project.pickle",
        cancel_markers=(tmp_path / "project.abandoned",),
        parent_pid=4242,
    )

    assert time.monotonic() - started < test_case.expected_max_seconds


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
