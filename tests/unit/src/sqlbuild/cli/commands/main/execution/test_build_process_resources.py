"""Tests for debug process reporting across build outcomes."""

from __future__ import annotations

from contextlib import nullcontext
from unittest.mock import Mock

import pytest

from sqlbuild.cli.commands.main.execution import _build as build_module
from sqlbuild.cli.commands.models import BuildCommandRequest
from sqlbuild.diagnostics.models import PartialBuildPhaseTimings
from tests.unit.src.sqlbuild.cli.commands.main.execution._test_types import (
    BuildPartialTimingOutputTestCase,
    BuildProcessReportTestCase,
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
    reporter: Mock = Mock()
    monkeypatch.setattr(build_module, "process_resource_reporting", reporter)
    reporter.return_value = nullcontext()
    monkeypatch.setattr(build_module, "_run_build", lambda **_kwargs: test_case.expected_exit_code)

    exit_code: int = build_module.run_build(BuildCommandRequest(debug=True))

    assert exit_code == test_case.expected_exit_code
    reporter.assert_called_once_with(enabled=True)


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
    reporter: Mock = Mock()

    def fail_build(**_kwargs: object) -> int:
        raise RuntimeError("build failed")

    monkeypatch.setattr(build_module, "process_resource_reporting", reporter)
    reporter.return_value = nullcontext()
    monkeypatch.setattr(build_module, "_run_build", fail_build)

    with pytest.raises(test_case.expected_error_type or RuntimeError):
        build_module.run_build(BuildCommandRequest(debug=True))

    reporter.assert_called_once_with(enabled=True)


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
    reporter: Mock = Mock()

    def interrupt_build(**_kwargs: object) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(build_module, "process_resource_reporting", reporter)
    reporter.return_value = nullcontext()
    monkeypatch.setattr(build_module, "_run_build", interrupt_build)

    with pytest.raises(test_case.expected_error_type or KeyboardInterrupt):
        build_module.run_build(BuildCommandRequest(debug=True))

    reporter.assert_called_once_with(enabled=True)


@pytest.mark.parametrize(
    "test_case",
    [
        BuildPartialTimingOutputTestCase(
            description="direct compile failure reports compile and total",
            error_type=RuntimeError,
            compile_seconds=1.0,
            planning_seconds=None,
            connection_seconds=None,
            execution_seconds=None,
            expected_fragments=("Phase timings", "compile", "total"),
            expected_absent_fragments=("planning", "connection preparation", "execution"),
        ),
        BuildPartialTimingOutputTestCase(
            description="virtual planning connection failure reports compile planning and total",
            error_type=RuntimeError,
            compile_seconds=1.0,
            planning_seconds=4.0,
            connection_seconds=None,
            execution_seconds=None,
            expected_fragments=("compile", "planning", "total"),
            expected_absent_fragments=("connection preparation", "execution"),
        ),
        BuildPartialTimingOutputTestCase(
            description="direct connection interruption reports preparation and total",
            error_type=KeyboardInterrupt,
            compile_seconds=1.0,
            planning_seconds=2.0,
            connection_seconds=3.0,
            execution_seconds=None,
            expected_fragments=("compile", "planning", "connection preparation", "total"),
            expected_absent_fragments=("execution",),
        ),
        BuildPartialTimingOutputTestCase(
            description="virtual execution interruption reports all available phases",
            error_type=KeyboardInterrupt,
            compile_seconds=1.0,
            planning_seconds=2.0,
            connection_seconds=3.0,
            execution_seconds=4.0,
            expected_fragments=(
                "compile",
                "planning",
                "connection preparation",
                "execution",
                "total",
            ),
            expected_absent_fragments=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_phase_failure_when_building_then_available_partial_timings_are_written(
    test_case: BuildPartialTimingOutputTestCase,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    timing_tracker: Mock = Mock()
    timing_tracker.snapshot.return_value = PartialBuildPhaseTimings(
        compile_seconds=test_case.compile_seconds,
        planning_seconds=test_case.planning_seconds,
        connection_preparation_seconds=test_case.connection_seconds,
        execution_seconds=test_case.execution_seconds,
        total_seconds=10.0,
    )
    timing_tracker.scope.return_value = nullcontext()

    def fail_build(**_kwargs: object) -> int:
        raise test_case.error_type("phase failed")

    monkeypatch.setattr(build_module, "BuildPhaseTimingTracker", lambda: timing_tracker)
    monkeypatch.setattr(build_module, "process_resource_reporting", lambda **_kwargs: nullcontext())
    monkeypatch.setattr(build_module, "_run_build", fail_build)

    with pytest.raises(test_case.error_type):
        build_module.run_build(BuildCommandRequest(verbose=True))

    output: str = capsys.readouterr().err
    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in output
    absent_fragment: str
    for absent_fragment in test_case.expected_absent_fragments:
        assert absent_fragment not in output
