from __future__ import annotations

import pytest

from sqlbuild.executor.scenario.classes.running_scenarios import RunningScenarios
from tests.unit.src.sqlbuild.executor.scenario.main._test_types import (
    RunningScenariosInterruptTestCase,
)
from tests.unit.src.sqlbuild.executor.scenario.main.helpers import (
    ScenarioInterruptTestAdapter,
    build_scenario_cleanup_test_plan,
)


@pytest.mark.parametrize(
    "test_case",
    [
        RunningScenariosInterruptTestCase(
            description="cancellable adapter interrupts only in-flight connections",
            cancellable=True,
            close_uncancellable=True,
            expected_events=("interrupt:busy",),
            expected_closed_connection=False,
        ),
        RunningScenariosInterruptTestCase(
            description="uncancellable adapter closes in-flight connections when stopping",
            cancellable=False,
            close_uncancellable=True,
            expected_events=("interrupt:busy", "close:busy"),
            expected_closed_connection=True,
        ),
        RunningScenariosInterruptTestCase(
            description="uncancellable adapter keeps connections on a signal-time cancel",
            cancellable=False,
            close_uncancellable=False,
            expected_events=("interrupt:busy",),
            expected_closed_connection=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_running_scenarios_when_interrupting_then_cancels_or_closes_in_flight_connections(
    test_case: RunningScenariosInterruptTestCase,
) -> None:
    adapter: ScenarioInterruptTestAdapter = ScenarioInterruptTestAdapter(
        cancellable=test_case.cancellable
    )
    running: RunningScenarios = RunningScenarios(adapter=adapter)
    running.start(scenario_plan=build_scenario_cleanup_test_plan(), connection="idle")
    running.finish(connection="idle")
    running.start(scenario_plan=build_scenario_cleanup_test_plan(), connection="busy")

    running.interrupt(close_uncancellable=test_case.close_uncancellable)

    assert tuple(adapter.events) == test_case.expected_events
    assert running.closed_connection is test_case.expected_closed_connection
    assert len(running.started_plans) == 2
