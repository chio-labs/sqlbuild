"""Tests for debug process reporting across build outcomes."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from sqlbuild.cli.commands.main.execution import _build as build_module
from sqlbuild.cli.commands.models import BuildCommandRequest
from sqlbuild.diagnostics.models import ProcessResourceUsage
from tests.unit.src.sqlbuild.cli.commands.main.execution._test_types import (
    BuildProcessReportTestCase,
)

_USAGE: ProcessResourceUsage = ProcessResourceUsage(
    wall_seconds=1.0,
    user_cpu_seconds=0.5,
    system_cpu_seconds=0.25,
    max_rss_bytes=1024,
)


@pytest.mark.parametrize(
    "test_case",
    [
        BuildProcessReportTestCase(
            description="successful debug build reports resources",
            expected_exit_code=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_successful_debug_build_when_finishing_then_reports_process_resources(
    test_case: BuildProcessReportTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracker: Mock = Mock()
    tracker.finish.return_value = _USAGE
    reporter: Mock = Mock()
    monkeypatch.setattr(build_module, "ProcessResourceTracker", lambda: tracker)
    monkeypatch.setattr(build_module, "log_process_resources", reporter)
    monkeypatch.setattr(build_module, "_run_build", lambda **_kwargs: test_case.expected_exit_code)

    exit_code: int = build_module.run_build(BuildCommandRequest(debug=True))

    assert exit_code == test_case.expected_exit_code
    reporter.assert_called_once_with(usage=_USAGE)


@pytest.mark.parametrize(
    "test_case",
    [
        BuildProcessReportTestCase(
            description="failed debug build reports resources",
            expected_error_type=RuntimeError,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_failed_debug_build_when_unwinding_then_reports_process_resources(
    test_case: BuildProcessReportTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracker: Mock = Mock()
    tracker.finish.return_value = _USAGE
    reporter: Mock = Mock()

    def fail_build(**_kwargs: object) -> int:
        raise RuntimeError("build failed")

    monkeypatch.setattr(build_module, "ProcessResourceTracker", lambda: tracker)
    monkeypatch.setattr(build_module, "log_process_resources", reporter)
    monkeypatch.setattr(build_module, "_run_build", fail_build)

    with pytest.raises(test_case.expected_error_type or RuntimeError):
        build_module.run_build(BuildCommandRequest(debug=True))

    reporter.assert_called_once_with(usage=_USAGE)


@pytest.mark.parametrize(
    "test_case",
    [
        BuildProcessReportTestCase(
            description="interrupted debug build reports resources",
            expected_error_type=KeyboardInterrupt,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_interrupted_debug_build_when_unwinding_then_reports_process_resources(
    test_case: BuildProcessReportTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracker: Mock = Mock()
    tracker.finish.return_value = _USAGE
    reporter: Mock = Mock()

    def interrupt_build(**_kwargs: object) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(build_module, "ProcessResourceTracker", lambda: tracker)
    monkeypatch.setattr(build_module, "log_process_resources", reporter)
    monkeypatch.setattr(build_module, "_run_build", interrupt_build)

    with pytest.raises(test_case.expected_error_type or KeyboardInterrupt):
        build_module.run_build(BuildCommandRequest(debug=True))

    reporter.assert_called_once_with(usage=_USAGE)
