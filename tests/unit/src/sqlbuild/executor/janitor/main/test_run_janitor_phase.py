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
    JanitorPhaseFlushFailureTestCase,
    JanitorPhaseInterruptTestCase,
    JanitorPhaseSubmitInterruptTestCase,
)
from tests.unit.src.sqlbuild.executor.janitor.main.helpers import (
    FailingPhaseActions,
    FailingReportProgress,
    PhaseActions,
    interrupting_submit,
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


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorPhaseSubmitInterruptTestCase(
            description="an interrupt while submitting still writes every completed event",
            connection_count=3,
            item_count=10,
            failing_submit=3,
            expected_error=KeyboardInterrupt,
            expected_maximum_completed=2,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_interrupt_while_submitting_when_running_phase_then_completed_actions_keep_events(
    test_case: JanitorPhaseSubmitInterruptTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actions: PhaseActions = PhaseActions()
    progress: FailingReportProgress = FailingReportProgress(
        failing_report=test_case.item_count + 1,
        error=BrokenPipeError,
        size=test_case.item_count,
    )
    monkeypatch.setattr(
        janitor_chunk_collector,
        "submit_janitor_action",
        interrupting_submit(
            janitor_chunk_collector.submit_janitor_action, failing_call=test_case.failing_submit
        ),
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

    assert len(actions.completed) <= test_case.expected_maximum_completed
    assert sorted(actions.flushed) == actions.completed_event_ids()
    assert progress.closed_failed == [True]


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorPhaseFlushFailureTestCase(
            description="a failed event write keeps the action failure and warns per schema",
            item_count=6,
            failing_item=3,
            action_error=RuntimeError,
            flush_error=OSError,
            expected_error=RuntimeError,
            expected_chained_error=OSError,
            expected_unwritten=((3, ("analytics",), "events table is locked"),),
        ),
        JanitorPhaseFlushFailureTestCase(
            description="an interrupted action still wins over a failed event write",
            item_count=6,
            failing_item=2,
            action_error=KeyboardInterrupt,
            flush_error=OSError,
            expected_error=KeyboardInterrupt,
            expected_chained_error=OSError,
            expected_unwritten=((2, ("analytics",), "events table is locked"),),
        ),
        JanitorPhaseFlushFailureTestCase(
            description="an interrupted event write wins over the action failure",
            item_count=6,
            failing_item=4,
            action_error=RuntimeError,
            flush_error=KeyboardInterrupt,
            expected_error=KeyboardInterrupt,
            expected_chained_error=RuntimeError,
            expected_unwritten=((4, ("analytics",), "events table is locked"),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_failing_event_write_when_phase_fails_then_original_error_is_raised_and_chained(
    test_case: JanitorPhaseFlushFailureTestCase,
) -> None:
    actions: FailingPhaseActions = FailingPhaseActions(
        failing_item=test_case.failing_item,
        error=test_case.action_error,
        flush_error=test_case.flush_error,
        size=test_case.item_count,
    )
    progress: FailingReportProgress = FailingReportProgress(
        failing_report=test_case.item_count + 1,
        error=BrokenPipeError,
        size=test_case.item_count,
    )

    with pytest.raises(test_case.expected_error) as raised:
        _ = run_janitor_phase(
            progress=progress,
            phase=JanitorPhase.ARCHIVE,
            items=tuple(range(test_case.item_count)),
            describe=phase_label,
            apply=actions.apply,
            workers=JanitorWorkers(connections=(object(),)),
            after_chunk=actions.flush,
        )

    assert isinstance(raised.value.__context__, test_case.expected_chained_error)
    assert progress.unwritten == list(test_case.expected_unwritten)
    assert progress.closed_failed == [True]
