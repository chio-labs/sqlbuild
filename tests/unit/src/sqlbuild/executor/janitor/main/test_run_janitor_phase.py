"""Every completed janitor action keeps its audit event when reporting or waiting fails."""

from __future__ import annotations

from concurrent.futures import wait

import pytest

from sqlbuild.executor.janitor.classes import janitor_chunk_collector
from sqlbuild.executor.janitor.classes.janitor_workers import JanitorWorkers
from sqlbuild.executor.janitor.main._run_janitor_phase import run_janitor_phase
from sqlbuild.executor.janitor.types import JanitorPhase
from tests.unit.src.sqlbuild.executor.janitor.main._test_types import (
    JanitorPhaseEventSafetyTestCase,
    JanitorPhaseInterruptTestCase,
)
from tests.unit.src.sqlbuild.executor.janitor.main.helpers import (
    FailingReportProgress,
    PhaseActions,
    interrupting_wait,
    phase_label,
)


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorPhaseEventSafetyTestCase(
            description="sequential actions keep their events when the progress stream breaks",
            connection_count=1,
            item_count=10,
            failing_report=3,
            report_error=BrokenPipeError,
            expected_error=BrokenPipeError,
            expected_minimum_completed=3,
        ),
        JanitorPhaseEventSafetyTestCase(
            description="concurrent actions keep their events when the progress stream breaks",
            connection_count=3,
            item_count=10,
            failing_report=3,
            report_error=BrokenPipeError,
            expected_error=BrokenPipeError,
            expected_minimum_completed=3,
        ),
        JanitorPhaseEventSafetyTestCase(
            description="an interrupt while reporting still writes every completed event",
            connection_count=3,
            item_count=10,
            failing_report=2,
            report_error=KeyboardInterrupt,
            expected_error=KeyboardInterrupt,
            expected_minimum_completed=2,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_failing_progress_when_running_phase_then_completed_actions_keep_events(
    test_case: JanitorPhaseEventSafetyTestCase,
) -> None:
    actions: PhaseActions = PhaseActions()
    progress: FailingReportProgress = FailingReportProgress(
        failing_report=test_case.failing_report,
        error=test_case.report_error,
        size=test_case.item_count,
    )

    with pytest.raises(test_case.expected_error):
        _ = run_janitor_phase(
            progress=progress,
            phase=JanitorPhase.ARCHIVE,
            items=tuple(range(test_case.item_count)),
            describe=phase_label,
            apply=actions.apply,
            workers=JanitorWorkers(
                connections=tuple(object() for _ in range(test_case.connection_count))
            ),
            after_chunk=actions.flush,
        )

    assert len(actions.completed) >= test_case.expected_minimum_completed
    assert len(actions.completed) < test_case.item_count
    assert sorted(actions.flushed) == actions.completed_event_ids()
    assert progress.closed_failed == [True]


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorPhaseInterruptTestCase(
            description="an interrupt while waiting for workers still writes completed events",
            connection_count=3,
            item_count=10,
            expected_error=KeyboardInterrupt,
            expected_minimum_completed=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_interrupt_while_waiting_when_running_phase_then_completed_actions_keep_events(
    test_case: JanitorPhaseInterruptTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actions: PhaseActions = PhaseActions()
    progress: FailingReportProgress = FailingReportProgress(
        failing_report=test_case.item_count + 1,
        error=BrokenPipeError,
        size=test_case.item_count,
    )
    monkeypatch.setattr(janitor_chunk_collector, "wait", interrupting_wait(wait))

    with pytest.raises(test_case.expected_error):
        _ = run_janitor_phase(
            progress=progress,
            phase=JanitorPhase.ARCHIVE,
            items=tuple(range(test_case.item_count)),
            describe=phase_label,
            apply=actions.apply,
            workers=JanitorWorkers(
                connections=tuple(object() for _ in range(test_case.connection_count))
            ),
            after_chunk=actions.flush,
        )

    assert len(actions.completed) >= test_case.expected_minimum_completed
    assert sorted(actions.flushed) == actions.completed_event_ids()
    assert progress.closed_failed == [True]
