"""Tests for non-degrading process resource diagnostics."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from sqlbuild.diagnostics.main import process_resource_reporting
from sqlbuild.diagnostics.models import ProcessResourceUsage
from tests.unit.src.sqlbuild.diagnostics.main._test_types import (
    ProcessReportingFailureTestCase,
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
        ProcessReportingFailureTestCase(
            description="tracker construction failure disables diagnostics",
            failure_stage="constructor",
            expected_tracker=False,
            expected_error_type=RuntimeError,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_tracker_constructor_failure_when_starting_then_diagnostics_are_disabled(
    test_case: ProcessReportingFailureTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_constructor() -> None:
        raise OSError(test_case.failure_stage)

    monkeypatch.setattr(process_resource_reporting, "ProcessResourceTracker", fail_constructor)

    with pytest.raises(test_case.expected_error_type or RuntimeError, match="original outcome"):
        with process_resource_reporting.process_resource_reporting(enabled=True):
            raise RuntimeError("original outcome")

    assert test_case.expected_tracker is False


@pytest.mark.parametrize(
    "test_case",
    [
        ProcessReportingFailureTestCase(
            description="finish sampling failure preserves original failure",
            failure_stage="finish",
            expected_tracker=True,
            expected_error_type=RuntimeError,
        ),
        ProcessReportingFailureTestCase(
            description="finish sampling failure preserves interruption",
            failure_stage="finish",
            expected_tracker=True,
            expected_error_type=KeyboardInterrupt,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_resource_diagnostic_failure_when_finishing_then_error_is_not_raised(
    test_case: ProcessReportingFailureTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracker: Mock = Mock()
    tracker.finish.side_effect = OSError(test_case.failure_stage)
    logger: Mock = Mock()
    monkeypatch.setattr(process_resource_reporting, "log_process_resources", logger)

    monkeypatch.setattr(
        process_resource_reporting, "ProcessResourceTracker", Mock(return_value=tracker)
    )

    with pytest.raises(test_case.expected_error_type or RuntimeError):
        with process_resource_reporting.process_resource_reporting(enabled=True):
            raise (test_case.expected_error_type or RuntimeError)("original outcome")

    assert test_case.expected_tracker


@pytest.mark.parametrize(
    "test_case",
    [
        ProcessReportingFailureTestCase(
            description="logger failure is ignored",
            failure_stage="logger",
            expected_tracker=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_resource_logger_failure_when_finishing_then_error_is_not_raised(
    test_case: ProcessReportingFailureTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracker: Mock = Mock()
    tracker.finish.return_value = _USAGE
    logger: Mock = Mock(side_effect=OSError(test_case.failure_stage))
    monkeypatch.setattr(process_resource_reporting, "log_process_resources", logger)

    monkeypatch.setattr(
        process_resource_reporting, "ProcessResourceTracker", Mock(return_value=tracker)
    )

    with process_resource_reporting.process_resource_reporting(enabled=True):
        pass

    assert test_case.expected_tracker
