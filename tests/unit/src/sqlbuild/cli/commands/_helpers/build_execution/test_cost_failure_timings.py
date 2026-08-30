"""Direct cost failure timing retention tests."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from sqlbuild.cli.commands._helpers.build_execution import completion, phase_timings
from sqlbuild.diagnostics.classes.build_phase_timing_tracker import BuildPhaseTimingTracker
from tests.unit.src.sqlbuild.cli.commands._helpers.build_execution._test_types import (
    CostFailureTimingTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CostFailureTimingTestCase(
            description="completed work retains cost elapsed when finalization fails",
            clock_values=(1.0, 4.0),
            expected_cost_seconds=3.0,
            expected_error_message="completed cost failure",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_completed_work_cost_failure_when_finalizing_then_elapsed_is_retained(
    test_case: CostFailureTimingTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monotonic: Mock = Mock(side_effect=test_case.clock_values)
    tracker: BuildPhaseTimingTracker = BuildPhaseTimingTracker(monotonic=lambda: 0.0)
    monkeypatch.setattr(completion.time, "monotonic", monotonic)
    monkeypatch.setattr(phase_timings.time, "monotonic", monotonic)
    monkeypatch.setattr(completion, "resolve_build_exit_code", Mock(return_value=0))
    monkeypatch.setattr(completion, "write_build_runtime_targets", Mock())
    monkeypatch.setattr(
        completion,
        "finalize_build_cost",
        Mock(side_effect=RuntimeError(test_case.expected_error_message)),
    )

    with tracker.scope(), pytest.raises(RuntimeError, match=test_case.expected_error_message):
        completion.complete_direct_build(
            request=Mock(),
            invocation=Mock(),
            pipeline_result=Mock(),
            preparation=Mock(),
            outcome=Mock(),
            check_results=(),
            build_started_at=datetime.now(UTC),
            command_started_at=0.0,
        )

    assert tracker.cost_collection_seconds == test_case.expected_cost_seconds


@pytest.mark.parametrize(
    "test_case",
    [
        CostFailureTimingTestCase(
            description="no-work build retains cost elapsed when finalization fails",
            clock_values=(2.0, 7.0),
            expected_cost_seconds=5.0,
            expected_error_message="no-work cost failure",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_no_work_cost_failure_when_finalizing_then_elapsed_is_retained(
    test_case: CostFailureTimingTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monotonic: Mock = Mock(side_effect=test_case.clock_values)
    tracker: BuildPhaseTimingTracker = BuildPhaseTimingTracker(monotonic=lambda: 0.0)
    monkeypatch.setattr(phase_timings.time, "monotonic", monotonic)
    monkeypatch.setattr(
        phase_timings,
        "finalize_no_work_build_if_needed",
        Mock(side_effect=RuntimeError(test_case.expected_error_message)),
    )

    with tracker.scope(), pytest.raises(RuntimeError, match=test_case.expected_error_message):
        phase_timings.finalize_no_work_with_timings(
            request=Mock(),
            invocation=Mock(),
            pipeline_result=Mock(),
            command_started_at=0.0,
        )

    assert tracker.cost_collection_seconds == test_case.expected_cost_seconds
